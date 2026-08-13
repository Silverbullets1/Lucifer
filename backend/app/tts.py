"""
Text-to-Speech for Lucifer — Voice Assistant backend.

VOICE POLICY (per SAM): ONLY Hindi, spoken by a natural Indian female voice.
  - Primary: Microsoft Edge TTS 'hi-IN-SwaraNeural' (free, no API key).
    Shaped per-reply by an EMOTION tag via SSML <mstts:express-as> +
    <prosody> (pitch / rate / volume / styledegree) so the voice sounds
    warm, playful, sad, angry, etc. instead of flat reading.
  - Fallback 1: gTTS Hindi (Google, free, natural) — used if Edge fails.
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

# Microsoft Edge TTS voice for Hindi (free, no API key)
EDGE_HI_VOICE = "hi-IN-SwaraNeural"  # Indian female (Devil's Queen), pure Hindi

# URLs / links — Edge reads these as awkward letter soup ("h t t p ...").
# We strip them from the SPOKEN text only (the on-screen reply keeps them).
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

# Trailing <EMOTION:..> tag the LLM appends so the voice can be shaped.
_EMOTION_TAG_RE = re.compile(r"\s*<EMOTION:([a-z]+)>\s*$", re.IGNORECASE)

# Emotion -> (Edge express-as style, pitch%, rate, volume, styledegree)
# styledegree (0.01-2, default 1) intensifies the emotion (2 = double).
# Values validated empirically against hi-IN-SwaraNeural (22 styles OK).
_EMOTION_MAP = {
    "loving":   ("affectionate", "+6%",  "0.95", "medium", "1.6"),
    "playful":  ("cheerful",     "+9%",  "1.05", "medium", "1.4"),
    "teasing":  ("gentle",       "+7%",  "1.0",  "medium", "1.3"),
    "sad":      ("sad",          "-12%", "0.82", "soft",   "1.8"),
    "angry":    ("angry",        "+5%",  "1.1",  "loud",   "1.6"),
    "calm":     ("calm",         "-3%",  "0.9",  "medium", "1.2"),
    "excited":  ("excited",      "+12%", "1.12", "loud",   "1.8"),
    "neutral":  (None,           "0%",   "1.0",  "medium", "1.0"),
}


def _strip_urls(text: str) -> str:
    """Replace spoken URLs with the word 'लिंक' so TTS doesn't read letter soup."""
    return _URL_RE.sub(" लिंक ", text)


def _split_emotion(text: str):
    """Return (clean_text, emotion) by extracting a trailing <EMOTION:..> tag."""
    m = _EMOTION_TAG_RE.search(text or "")
    if m:
        return text[: m.start()].strip(), m.group(1).lower()
    return (text or "").strip(), "neutral"


def _build_ssml(text: str, voice: str, emotion: str = "neutral") -> str:
    """Build Edge-compatible SSML with emotion shaping.

    NESTING MATTERS: <prosody> must wrap <express-as> (prosody OUTSIDE).
    If prosody is nested INSIDE express-as, the style overrides pitch/rate
    and they are ignored. Verified empirically: prosody-outside gives the
    intended F0 shift; prosody-inside does not.
    """
    style, pitch, rate, volume, degree = _EMOTION_MAP.get(
        emotion, _EMOTION_MAP["neutral"]
    )
    if style:
        inner = (
            f'<prosody pitch="{pitch}" rate="{rate}" volume="{volume}">'
            f'<mstts:express-as style="{style}" styledegree="{degree}">'
            f"{text}</mstts:express-as></prosody>"
        )
    else:
        inner = f'<prosody pitch="{pitch}" rate="{rate}" volume="{volume}">{text}</prosody>'
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="hi-IN">'
        f'<voice name="{voice}">{inner}</voice></speak>'
    )


async def _edge_tts_ssml(text: str, voice: str, emotion: str = "neutral",
                         retries: int = 3) -> bytes:
    import edge_tts

    ssml = _build_ssml(text, voice, emotion)
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
    """Free Google TTS Hindi — natural, better than Kokoro robotic fallback."""
    from gtts import gTTS

    buf = io.BytesIO()
    gTTS(text=text, lang="hi", slow=False).write_to_fp(buf)
    return buf.getvalue()


def _kokoro_hindi_fallback(text: str, settings: Settings) -> bytes:
    """Offline Kokoro Hindi (hm_psi) — last resort if both cloud TTS fail.

    Produces a raw float waveform; we wrap it as 16-bit PCM WAV.
    """
    import numpy as np
    import soundfile as sf  # Kokoro returns audio; we re-encode to WAV

    from kokoro import KPipeline

    pipe = KPipeline(lang_code="h")  # 'h' = Hindi
    # Kokoro streams; collect the first (only) generator result.
    audio_segments = []
    generator = pipe(text, voice="hm_psi", speed=1.0)
    for _i, (gs, ps, audio) in enumerate(generator):
        audio_segments.append(audio)
    if not audio_segments:
        raise RuntimeError("Kokoro produced no audio")
    audio = np.concatenate(audio_segments)
    # Kokoro output is 24kHz float; write to in-memory WAV.
    buf = io.BytesIO()
    sf.write(buf, audio, 24000, format="WAV")
    return buf.getvalue()


async def synthesize(text: str, settings: Settings,
                    emotion: str = "neutral") -> bytes:
    """All replies spoken by Swara (hi-IN). Emotion shapes the voice via SSML.

    Fallback chain: Edge Swara (SSML, emotion-shaped)
                    -> gTTS Hindi (natural)
                    -> Kokoro Hindi (offline, last resort).
    """
    if not text.strip():
        return b""
    clean, emotion = _split_emotion(text)
    clean = _strip_urls(clean)  # don't speak "h t t p ..."
    # If the cleaned text became empty (e.g. only a URL), say a gentle filler.
    if not clean.strip():
        clean = "लिंक मिला"
    try:
        return await _edge_tts_ssml(clean, EDGE_HI_VOICE, emotion=emotion)
    except Exception as e:  # noqa: BLE001
        log.warning("Edge TTS failed (%s); trying gTTS Hindi", e)
        try:
            return await asyncio.to_thread(_gtts_hindi_fallback, clean)
        except Exception as e2:  # noqa: BLE001
            log.warning("gTTS failed (%s); falling back to Kokoro Hindi", e2)
            return await asyncio.to_thread(_kokoro_hindi_fallback, clean, settings)
