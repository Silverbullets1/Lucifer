"""
Text-to-Speech for Lucifer - Voice Assistant backend.

VOICE POLICY (per SAM, restored + reinforced Aug 2026):
  PRIMARY : Sarvam Bulbul V3, speaker=shubh (Indian MALE, native Hinglish, hi-IN)
  FALLBACK: Edge TTS en-IN-PrabhatNeural (free, no key) if Sarvam fails
  FALLBACK2: gTTS English, then Kokoro en_IN offline as last resort.

Sarvam request (proven, 200 + mp3):
  POST https://api.sarvam.ai/text-to-speech
  Authorization: Bearer <SARVAM_API_KEY>
  {text, target_language_code:"hi-IN", speaker:"shubh",
   model:"bulbul:v3", output_audio_codec:"mp3", pace:1.0}
  PITFALL: bulbul:v3 rejects pitch/loudness (HTTP 400) - never send them.
"""
from __future__ import annotations

import io
import logging
import re
import asyncio
import os

from .config import Settings

log = logging.getLogger("lucifer.tts")

# Microsoft Edge TTS voice for Hinglish (free, no API key) - fallback
EDGE_HI_VOICE = "en-IN-PrabhatNeural"

# Sarvam Bulbul V3 (primary, native Hinglish male)
_SARVAM_URL = "https://api.sarvam.ai/text-to-speech"


def _strip_urls(text: str) -> str:
    """Replace spoken URLs with ' link ' so TTS does not read letter soup."""
    return re.sub(r"https?://\S+|https?:\S+|www\.\S+", " link ", text, flags=re.IGNORECASE)


async def _sarvam_tts(text: str, settings: Settings, retries: int = 2) -> bytes:
    import httpx
    key = os.environ.get("SARVAM_API_KEY") or getattr(settings, "brain_api_key", "")
    if not key:
        raise RuntimeError("SARVAM_API_KEY not set")
    speaker = os.environ.get("SARVAM_SPEAKER") or "shubh"
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    _SARVAM_URL,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "text": text,
                        "target_language_code": "hi-IN",
                        "speaker": speaker,
                        "model": "bulbul:v3",
                        "output_audio_codec": "mp3",
                        "pace": 1.0,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    audio = data.get("audios") or data.get("audio") or ""
                    if isinstance(audio, list):
                        audio = audio[0] if audio else ""
                    if audio:
                        import base64
                        return base64.b64decode(audio)
                last_err = RuntimeError(f"Sarvam HTTP {resp.status_code}: {resp.text[:120]}")
        except Exception as e:  # noqa: BLE001
            last_err = e
            log.warning("Sarvam TTS attempt %d/%d failed: %s", attempt, retries, e)
    raise last_err or RuntimeError("sarvam failed")


async def _edge_tts(text: str, voice: str, retries: int = 3) -> bytes:
    import edge_tts
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            communicate = edge_tts.Communicate(text, voice, rate="+15%", volume="+20%", pitch="-6Hz")
            buf = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            data = buf.getvalue()
            if data:
                return data
            last_err = RuntimeError("empty audio from Edge")
        except Exception as e:  # noqa: BLE001
            last_err = e
            log.warning("Edge TTS attempt %d/%d failed: %s", attempt, retries, e)
    raise last_err or RuntimeError("edge_tts failed")


def _gtts_hindi_fallback(text: str) -> bytes:
    from gtts import gTTS
    buf = io.BytesIO()
    gTTS(text=text, lang="en", slow=False).write_to_fp(buf)
    return buf.getvalue()


def _kokoro_hindi_fallback(text: str, settings: Settings) -> bytes:
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline
    pipe = KPipeline(lang_code="e")
    audio_segments = []
    for _i, (gs, ps, audio) in enumerate(pipe(text, voice="en_IN_001", speed=1.0)):
        audio_segments.append(audio)
    if not audio_segments:
        raise RuntimeError("Kokoro produced no audio")
    audio = np.concatenate(audio_segments)
    buf = io.BytesIO()
    sf.write(buf, audio, 24000, format="WAV")
    return buf.getvalue()


async def synthesize(text: str, settings: Settings) -> bytes:
    """Speak text with Sarvam shubh (primary) then Edge, gTTS, Kokoro."""
    if not text.strip():
        return b""
    clean = _strip_urls(text.strip())
    if not clean.strip():
        clean = "लिंक मिला"
    try:
        return await _sarvam_tts(clean, settings)
    except Exception as e:  # noqa: BLE001
        log.warning("Sarvam failed (%s); trying Edge", e)
    try:
        return await _edge_tts(clean, EDGE_HI_VOICE)
    except Exception as e:  # noqa: BLE001
        log.warning("Edge failed (%s); trying gTTS", e)
    try:
        return await asyncio.to_thread(_gtts_hindi_fallback, clean)
    except Exception as e2:  # noqa: BLE001
        log.warning("gTTS failed (%s); trying Kokoro", e2)
    return await asyncio.to_thread(_kokoro_hindi_fallback, clean, settings)
