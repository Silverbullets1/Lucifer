"""
Text-to-Speech for Lucifer.

VOICE POLICY (per SAM): ONLY Hindi / Hinglish.
  - Every reply (Hindi, Hinglish, or even English text) is spoken by
    Microsoft Edge TTS 'hi-IN-ArjunNeural' — a natural Indian male voice
    that reads Hinglish smoothly. No English/USA-accent voice anywhere.
  - Kokoro Hindi (hm_psi) is kept ONLY as an offline fallback if Edge fails.

synthesize() is async because the FastAPI event loop is already running,
so we must `await` edge_tts rather than asyncio.run().
"""
from __future__ import annotations
import io, logging, re, asyncio
from .config import Settings

log = logging.getLogger("lucifer.tts")

# Devanagari range = Hindi written in देवनागरी
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")

# URLs / links — Edge reads these as awkward letter soup ("h t t p...").
# We strip them from the SPOKEN text only (the on-screen reply keeps them).
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


def _strip_urls(text: str) -> str:
    return _URL_RE.sub(" लिंक ", text)

# Microsoft Edge TTS voice for Hindi (free, no API key)
EDGE_HI_VOICE = "hi-IN-SwaraNeural"  # Indian female (Devil's Queen), pure Hindi

_PIPES = {}  # lang_code -> KPipeline (lazy, fallback only)


def _has_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI.search(text))


def _get_pipe(lang_code: str):
    if lang_code not in _PIPES:
        from kokoro import KPipeline
        _PIPES[lang_code] = KPipeline(lang_code=lang_code)
    return _PIPES[lang_code]


async def _edge_tts(text: str, voice: str, retries: int = 3) -> bytes:
    return await _edge_tts_ssml(text, voice, retries)


# Emotion -> Edge express-as style + prosody (pitch%, rate, volume)
# Gives the voice real warmth/playfulness/sadness instead of flat reading.
_EMOTION_MAP = {
    "loving":   ("affectionate", "+6%", "0.95"),
    "playful":  ("cheerful",    "+9%", "1.05"),
    "teasing":  ("gentle",      "+7%", "1.0"),
    "sad":      ("sad",         "-10%", "0.85"),
    "angry":    ("angry",       "+4%", "1.1"),
    "calm":     ("calm",        "0%",  "0.9"),
    "excited":  ("cheerful",    "+12%", "1.12"),
    "neutral":  (None,          "0%",  "1.0"),
}


def _build_ssml(text: str, voice: str, emotion: str = "neutral") -> str:
    style, pitch, rate = _EMOTION_MAP.get(emotion, _EMOTION_MAP["neutral"])
    # strip inline EMOTION tag if present in text
    clean = re.sub(r"<EMOTION:[a-z]+>\s*$", "", text.strip())
    if style:
        inner = f'<mstts:express-as style="{style}">{clean}</mstts:express-as>'
    else:
        inner = clean
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="hi-IN">'
        f'<voice name="{voice}"><prosody pitch="{pitch}" rate="{rate}">'
        f'{inner}</prosody></voice></speak>'
    )


async def _edge_tts_ssml(text: str, voice: str, retries: int = 3,
                         emotion: str = "neutral") -> bytes:
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
        except Exception as e:
            last_err = e
            log.warning("Edge TTS attempt %d/%d failed: %s", attempt, retries, e)
    raise last_err or RuntimeError("edge_tts failed")


def _gtts_hindi_fallback(text: str) -> bytes:
    """Free Google TTS Hindi — natural, better than Kokoro robotic fallback."""
    from gtts import gTTS
    import io
    buf = io.BytesIO()
    gTTS(text=text, lang="hi", slow=False).write_to_fp(buf)
    return buf.getvalue()


async def synthesize(text: str, settings: Settings, emotion: str = "neutral") -> bytes:
    """ALL replies spoken by Swara (hi-IN). Emotion shapes the voice via SSML.
    Fallback chain: Edge Swara(SSML) -> gTTS Hindi (natural) -> Kokoro Hindi."""
    if not text.strip():
        return b""
    clean = re.sub(r"<EMOTION:[a-z]+>\s*$", "", text.strip())
    clean = _strip_urls(clean)   # don't speak "h t t p..."
    try:
        return await _edge_tts_ssml(clean, EDGE_HI_VOICE, emotion=emotion)
    except Exception as e:
        log.warning("Edge TTS failed (%s); trying gTTS Hindi", e)
        try:
            return await asyncio.to_thread(_gtts_hindi_fallback, clean)
        except Exception as e2:
            log.warning("gTTS failed (%s); falling back to Kokoro Hindi", e2)
            return await asyncio.to_thread(_kokoro_hindi_fallback, clean, settings)


def _to_wav_bytes(audio_float, sample_rate: int) -> bytes:
    import numpy as np
    audio_int = (np.clip(audio_float, -1.0, 1.0) * 32767).astype("<i2")
    buf = io.BytesIO()
    with __import__("wave").open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int.tobytes())
    return buf.getvalue()
