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
    import edge_tts
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            communicate = edge_tts.Communicate(text, voice)
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


async def synthesize(text: str, settings: Settings) -> bytes:
    """ALL replies spoken by Arjun (hi-IN). No English/USA voice, ever.
    Fallback chain: Edge Arjun -> gTTS Hindi (natural) -> Kokoro Hindi (offline)."""
    if not text.strip():
        return b""
    try:
        return await _edge_tts(text, EDGE_HI_VOICE)
    except Exception as e:
        log.warning("Edge TTS failed (%s); trying gTTS Hindi", e)
        try:
            return await asyncio.to_thread(_gtts_hindi_fallback, text)
        except Exception as e2:
            log.warning("gTTS failed (%s); falling back to Kokoro Hindi", e2)
            return await asyncio.to_thread(_kokoro_hindi_fallback, text, settings)


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
