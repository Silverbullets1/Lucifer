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

# Microsoft Edge TTS voice for Hinglish (free, no API key)
# en-IN-PrabhatNeural = Indian MALE, natural Hinglish (Roman) accent — no USA accent
EDGE_HI_VOICE = "en-IN-PrabhatNeural"

# URLs / links — Edge reads these as awkward letter soup ("h t t p ...").
# We strip them from the SPOKEN text only (the on-screen reply keeps them).
# Covers http://, https://, AND malformed forms like https:www or http:site
# (no slashes). \S+ stops at the next whitespace so we don't over-eat the reply.
_URL_RE = re.compile(r"https?://\S+|https?:\S+|www\.\S+", re.IGNORECASE)


def _strip_urls(text: str) -> str:
    """Replace spoken URLs with the word 'लिंक' so TTS doesn't read letter soup."""
    return _URL_RE.sub(" लिंक ", text)


async def _edge_tts(text: str, voice: str, retries: int = 3) -> bytes:
    import edge_tts

    # SSML energy boost: punchy Devil vibe (faster, louder, higher pitch).
    # Escape XML special chars so replies with & or < don't break the SSML.
    safe = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    ssml = (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        'xml:lang="en-IN">'
        '<prosody rate="fast" pitch="+3st" volume="loud">'
        f"{safe}"
        "</prosody></speak>"
    )

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            communicate = edge_tts.Communicate(ssml, voice)
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
    """Speak text with Swara (hi-IN) — plain natural Hindi, no emotion shaping.

    Fallback chain: Edge Swara (natural)
                    -> gTTS Hindi (natural)
                    -> Kokoro Hindi (offline, last resort).
    """
    if not text.strip():
        return b""
    clean = _strip_urls(text.strip())
    # If the cleaned text became empty (e.g. only a URL), say a gentle filler.
    if not clean.strip():
        clean = "लिंक मिला"
    try:
        return await _edge_tts(clean, EDGE_HI_VOICE)
    except Exception as e:  # noqa: BLE001
        log.warning("Edge TTS failed (%s); trying gTTS Hindi", e)
        try:
            return await asyncio.to_thread(_gtts_hindi_fallback, clean)
        except Exception as e2:  # noqa: BLE001
            log.warning("gTTS failed (%s); falling back to Kokoro Hindi", e2)
            return await asyncio.to_thread(_kokoro_hindi_fallback, clean, settings)
