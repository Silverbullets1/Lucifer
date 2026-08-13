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

# Microsoft Edge TTS voice for Hindi/Hinglish (free, no API key)
EDGE_HI_VOICE = "hi-IN-ArjunNeural"

_PIPES = {}  # lang_code -> KPipeline (lazy, fallback only)


def _has_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI.search(text))


def _get_pipe(lang_code: str):
    if lang_code not in _PIPES:
        from kokoro import KPipeline
        _PIPES[lang_code] = KPipeline(lang_code=lang_code)
    return _PIPES[lang_code]


async def _edge_tts(text: str, voice: str) -> bytes:
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()


def _kokoro_hindi_fallback(text: str, settings: Settings) -> bytes:
    """Offline fallback only — Hindi voice, never English."""
    from indic_transliteration.sanscript import transliterate, OPTITRANS, DEVANAGARI
    import numpy as np
    pipe = _get_pipe("h")
    try:
        synth_text = transliterate(text, OPTITRANS, DEVANAGARI)
    except Exception:
        synth_text = text
    wavs = [audio for _, _, audio in pipe(synth_text, voice=settings.tts_voice_hi, speed=1.0) if audio is not None]
    if not wavs:
        return b""
    audio = np.concatenate(wavs) if len(wavs) > 1 else wavs[0]
    if hasattr(audio, "cpu"):
        audio = audio.cpu().numpy()
    return _to_wav_bytes(audio, sample_rate=24000)


async def synthesize(text: str, settings: Settings) -> bytes:
    """ALL replies spoken by Arjun (hi-IN). No English/USA voice, ever."""
    if not text.strip():
        return b""
    try:
        return await _edge_tts(text, EDGE_HI_VOICE)
    except Exception as e:
        log.warning("Edge TTS failed (%s); falling back to Kokoro Hindi", e)
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
