"""
Text-to-Speech for Lucifer — Voice Assistant backend.

VOICE POLICY (per SAM): ONLY Hindi, spoken by a natural Indian female voice.
  - Primary: Microsoft Edge TTS 'hi-IN-SwaraNeural' (free, no API key).
    Plain, natural Hindi speech — the most human-sounding free option.
  - Fallback 1: gTTS Hindi (Google, free, natural) — if Edge fails.
  - Fallback 2: Kokoro Hindi (offline) — last resort if both cloud TTS fail.

synthesize() is async because the FastAPI event loop is already running,
so we must `await` edge_tts rather than asyncio.run().
"""
from __future__ import annotations

import io
import logging
import re
import asyncio

from .config import Settings

log = logging.getLogger("lucifer.tts")

# Microsoft Edge TTS voice for Hinglish (fallback, free, no API key)
# en-IN-PrabhatNeural = Indian MALE, natural Hinglish (Roman) accent — no USA accent
EDGE_HI_VOICE = "en-IN-PrabhatNeural"

# Sarvam Bulbul V3 (primary) — Kabir = Indian MALE, native Hinglish code-switching.
# Api key + speaker come from Settings (env). Hinglish mixing is far more natural
# here than on Edge, so this is the primary voice per SAM's choice.
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"

# URLs / links — Edge reads these as awkward letter soup ("h t t p ...").
# We strip them from the SPOKEN text only (the on-screen reply keeps them).
# Covers http://, https://, AND malformed forms like https:www or http:site
# (no slashes). \S+ stops at the next whitespace so we don't over-eat the reply.
_URL_RE = re.compile(r"https?://\S+|https?:\S+|www\.\S+", re.IGNORECASE)


def _strip_urls(text: str) -> str:
    """Replace spoken URLs with the word 'link' so TTS doesn't read letter soup.
    Use English 'link' (not Hindi 'लिंक') so the Hinglish male voice reads it cleanly."""
    return _URL_RE.sub(" link ", text)


async def _edge_tts(text: str, voice: str, retries: int = 3) -> bytes:
    import edge_tts

    # Native prosody params (edge_tts supports rate/volume/pitch directly —
    # wrapping in SSML made Edge read the tags aloud as text, a bug).
    # rate="+15%" + louder + lower pitch = punchy male Devil vibe.
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            communicate = edge_tts.Communicate(
                text,
                voice,
                rate="+15%",
                volume="+20%",
                pitch="-6Hz",
            )
            buf = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            data = buf.getvalue()
            if data:
                return data
            last_err = RuntimeError("empty audio from Edge")
        except Exception as e:  # noqa: BLE001 - we retry regardless of type
            last_err = e
            log.warning("Edge TTS attempt %d/%d failed: %s", attempt, retries, e)
    raise last_err or RuntimeError("edge_tts failed")


def _sarvam_tts(text: str, settings: Settings) -> bytes:
    """Sarvam Bulbul V3 — Kabir (Indian MALE, native Hinglish code-switching).

    Sarvam returns base64-encoded audio inside a JSON `audios` array, so we
    must decode it (saving the raw response directly yields a non-playable
    JSON file, not mp3). hi-IN target language gives natural Hinglish mixing.
    """
    import base64
    import subprocess
    import requests

    if not settings.sarvam_api_key:
        raise RuntimeError("SARVAM_API_KEY not set")

    resp = requests.post(
        SARVAM_TTS_URL,
        headers={
            "api-subscription-key": settings.sarvam_api_key,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "target_language_code": "hi-IN",
            "speaker": settings.sarvam_speaker,
            "model": "bulbul:v3",
            "output_audio_codec": "mp3",
        },
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Sarvam API error {resp.status_code}: {resp.text[:200]}")
    payload = resp.json()
    audios = payload.get("audios") or []
    if not audios:
        raise RuntimeError("Sarvam returned no audio")
    audio = base64.b64decode(audios[0])
    # Speed up + brighten Kabir for a punchier, energetic Devil vibe.
    # atempo 1.15 = ~15% faster; highpass removes mud -> brighter/energetic.
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", "pipe:0", "-af",
             "highpass=f=120,atempo=1.15", "-f", "mp3", "pipe:1"],
            input=audio, capture_output=True, timeout=30,
        )
        if proc.returncode == 0 and proc.stdout:
            audio = proc.stdout
    except Exception as e:
        log.warning("kabir speedup ffmpeg skipped: %s", e)
    return audio


def _gtts_hindi_fallback(text: str) -> bytes:
    """Free Google TTS — for Hinglish we use English (en) so it doesn't read
    Roman Hindi with a USA accent. Natural enough as a fallback."""
    from gtts import gTTS

    buf = io.BytesIO()
    gTTS(text=text, lang="en", slow=False).write_to_fp(buf)
    return buf.getvalue()


def _kokoro_hindi_fallback(text: str, settings: Settings) -> bytes:
    """Offline Kokoro English-India (en IN) — last resort for Hinglish text.

    Produces a raw float waveform; we wrap it as 16-bit PCM WAV.
    """
    import numpy as np
    import soundfile as sf  # Kokoro returns audio; we re-encode to WAV

    from kokoro import KPipeline

    pipe = KPipeline(lang_code="e")  # 'e' = English (kokoro has no hi/IN; en is closest)
    audio_segments = []
    generator = pipe(text, voice="en_IN_001", speed=1.0)
    for _i, (gs, ps, audio) in enumerate(generator):
        audio_segments.append(audio)
    if not audio_segments:
        raise RuntimeError("Kokoro produced no audio")
    audio = np.concatenate(audio_segments)
    buf = io.BytesIO()
    sf.write(buf, audio, 24000, format="WAV")
    return buf.getvalue()


async def synthesize(text: str, settings: Settings) -> bytes:
    """Speak text with Kabir (Sarvam Bulbul V3) — Indian MALE, native Hinglish.

    Fallback chain: Sarvam Kabir (natural Hinglish, PRIMARY)
                    -> Edge Prabhat (Indian male Hinglish, if Sarvam fails)
                    -> gTTS Hindi (natural)
                    -> Kokoro Hindi (offline, last resort).
    """
    if not text.strip():
        return b""
    clean = _strip_urls(text.strip())
    # If the cleaned text became empty (e.g. only a URL), say a gentle filler.
    if not clean.strip():
        clean = "लिंक मिला"
    # Primary: Sarvam Bulbul V3 (Kabir) — best Hinglish male voice
    try:
        return await asyncio.to_thread(_sarvam_tts, clean, settings)
    except Exception as e:  # noqa: BLE001
        log.warning("Sarvam TTS failed (%s); trying Edge Prabhat", e)
    # Fallback 1: Edge Prabhat (Indian male Hinglish)
    try:
        return await _edge_tts(clean, settings.edge_hi_voice)
    except Exception as e:  # noqa: BLE001
        log.warning("Edge TTS failed (%s); trying gTTS Hindi", e)
    # Fallback 2: gTTS Hindi
    try:
        return await asyncio.to_thread(_gtts_hindi_fallback, clean)
    except Exception as e2:  # noqa: BLE001
        log.warning("gTTS failed (%s); falling back to Kokoro Hindi", e2)
        return await asyncio.to_thread(_kokoro_hindi_fallback, clean, settings)
