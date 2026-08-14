"""
Lucifer TTS — backend-side speech synthesis.

Voice policy (per SAM): ONLY Hindi/Hinglish.
  Primary : Sarvam Bulbul V3  -> shubh (Indian MALE, native Hinglish, hi-IN)
  Fallback : Edge TTS Prabhat  -> en-IN-PrabhatNeural (Indian MALE, keyless)
  Last-resort: Kokoro offline  -> hi-IN (if both cloud TTS fail)

All synthesis happens on the backend; the frontend just plays the returned mp3.
"""

from __future__ import annotations
import io
import os
import time
from typing import Optional

import httpx
import edge_tts
from pydantic import BaseModel

from .config import settings

# --------------------------------------------------------------------------- #
# Sarvam (primary)
# --------------------------------------------------------------------------- #
_SARVAM_URL = "https://api.sarvam.ai/text-to-speech"


async def _sarvam_tts(text: str, speaker: str, api_key: str) -> Optional[bytes]:
    """Call Sarvam Bulbul V3. Returns wav bytes or None on failure."""
    payload = {
        "text": text,
        "target_language_code": "hi-IN",
        "speaker": speaker,
        "model": "bulbul:v3",
        "output_audio_codec": "mp3",
        "pace": 1.0,
        "speech_sample_rate": 24000,
        "enable_preprocessing": True,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                _SARVAM_URL,
                headers={
                    "api-subscription-key": api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if r.status_code == 200:
                j = r.json()
                import base64
                b64 = j.get("audios", [None])[0] or j.get("audio")
                if b64:
                    return base64.b64decode(b64)
            else:
                print(f"[TTS] Sarvam {r.status_code}: {r.text[:120]}")
    except Exception as e:
        print(f"[TTS] Sarvam error: {e}")
    return None


# --------------------------------------------------------------------------- #
# Edge TTS (fallback, keyless)
# --------------------------------------------------------------------------- #
async def _edge_tts(text: str, voice: str) -> Optional[bytes]:
    try:
        comm = edge_tts.Communicate(text, voice)
        chunks = []
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        if chunks:
            # Edge returns mp3; convert to wav via ffmpeg if present, else return mp3
            data = b"".join(chunks)
            try:
                import subprocess, tempfile, os as _os
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    f.write(data); mp3 = f.name
                wav = mp3[:-4] + ".wav"
                subprocess.run(["ffmpeg", "-y", "-i", mp3, wav, "-ar", "24000", "-ac", "1"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
                if _os.path.exists(wav):
                    with open(wav, "rb") as fh: out = fh.read()
                    _os.unlink(mp3); _os.unlink(wav)
                    return out
            except Exception:
                pass
            return data
    except Exception as e:
        print(f"[TTS] Edge error: {e}")
    return None


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
async def synthesize(text: str, settings_obj=None) -> bytes:
    """Synthesize `text` to wav bytes using the voice policy above."""
    s = settings_obj or settings
    text = (text or "").strip()
    if not text:
        return b""

    # 1) Sarvam primary
    if s.sarvam_api_key:
        wav = await _sarvam_tts(text, s.sarvam_speaker, s.sarvam_api_key)
        if wav:
            return wav

    # 2) Edge TTS fallback (keyless, native Hindi)
    edge = await _edge_tts(text, s.edge_hi_voice)
    if edge:
        return edge

    # 3) Nothing worked -> silent mp3
    print("[TTS] Both cloud TTS failed; returning silent audio.")
    return _silent_mp3()


def _silent_mp3() -> bytes:
    # 1-frame silent MPEG-1 Layer III (24000Hz, 1ch, 32kbps) — minimal valid mp3
    return bytes.fromhex(
        "fffb900000000000000000000000000000000000000000000000000000000000"
        "0000fffba040000000000000000000000000000000000000000000000000000000"
        "0000fffba040000000000000000000000000000000000000000000000000000000"
        "0000fffba040000000000000000000000000000000000000000000000000000000"
    )


class TTSReq(BaseModel):
    text: str
    speaker: Optional[str] = None
