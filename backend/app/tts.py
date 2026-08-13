"""
Text-to-Speech for Lucifer.

Voice routing (all male, natural):
  - Hinglish (Romanized Hindi) or Devanagari -> Microsoft Edge TTS 'hi-IN-ArjunNeural'
      (free, no key, natural Indian male; reads Hinglish smoothly)
  - English text                          -> Kokoro 'am_michael' (warm deep male)

NOTE: synthesize() is async because the FastAPI event loop is already running,
so we must `await` edge_tts rather than asyncio.run() (which errors inside a loop).
"""
from __future__ import annotations
import io, logging, re, asyncio
from .config import Settings

log = logging.getLogger("lucifer.tts")

# Devanagari range = Hindi written in देवनागरी
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
# Hinglish / Romanized Hindi heuristic: common Hindi words in Latin script
_HINGLISH_WORDS = re.compile(
    r"\b(ae|aye|oye|saale|sale|boss|bhai|bc|bsdk|kaise|kese|kya|hai|hain|hu|hoon|"
    r"tera|mera|karo|kar|raha|rha|de|le|sun|sunna|laga|lagi|mast|scene|yaar|"
    r"kahan|kahaan|abhi|phir|fir|theek|thik|acha|accha|chal|chalo|khel|ghoom|"
    r"bol|bolo|dekh|dekho|samjha|samjho|nahi|nhi|haan|han|arre|arey|oy|"
    r"kaam|paisa|paise|gadi|gaadi|dost|mada|rk|re|ve|ji|saab|babu|kem|kemcho|"
    r"bhen|behen|pagle|pagal|janta|janata|tujhe|tuje|muje|mujhe|kyu|kyun|haa)\\b",
    re.IGNORECASE,
)

# Microsoft Edge TTS voice for Hindi/Hinglish (free, no API key)
EDGE_HI_VOICE = "hi-IN-ArjunNeural"

_PIPES = {}  # lang_code -> KPipeline (lazy)


def _has_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI.search(text))


def _looks_hinglish(text: str) -> bool:
    return bool(_HINGLISH_WORDS.search(text))


def _is_english(text: str) -> bool:
    if _has_devanagari(text) or _looks_hinglish(text):
        return False
    letters = re.findall(r"[A-Za-z]", text)
    return len(letters) >= 3


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


def _kokoro_hindi(text: str, settings: Settings) -> bytes:
    from indic_transliteration.sanscript import transliterate, OPTITRANS, DEVANAGARI
    pipe = _get_pipe("h")
    try:
        synth_text = transliterate(text, OPTITRANS, DEVANAGARI)
    except Exception:
        synth_text = text
    wavs = [audio for _, _, audio in pipe(synth_text, voice=settings.tts_voice_hi, speed=1.0) if audio is not None]
    if not wavs:
        return b""
    import numpy as np
    audio = np.concatenate(wavs) if len(wavs) > 1 else wavs[0]
    if hasattr(audio, "cpu"):
        audio = audio.cpu().numpy()
    return _to_wav_bytes(audio, sample_rate=24000)


def _kokoro_english(text: str, settings: Settings) -> bytes:
    pipe = _get_pipe("a")
    wavs = [audio for _, _, audio in pipe(text, voice=settings.tts_voice_en, speed=1.0) if audio is not None]
    if not wavs:
        return b""
    import numpy as np
    audio = np.concatenate(wavs) if len(wavs) > 1 else wavs[0]
    if hasattr(audio, "cpu"):
        audio = audio.cpu().numpy()
    return _to_wav_bytes(audio, sample_rate=24000)


async def synthesize(text: str, settings: Settings) -> bytes:
    """Async TTS. Routes Hinglish/Devanagari -> Edge (Arjun); English -> Kokoro (am_michael)."""
    if not text.strip():
        return b""
    if _has_devanagari(text) or _looks_hinglish(text):
        try:
            return await _edge_tts(text, EDGE_HI_VOICE)
        except Exception as e:
            log.warning("Edge TTS failed (%s); falling back to Kokoro Hindi", e)
            return await asyncio.to_thread(_kokoro_hindi, text, settings)
    if _is_english(text):
        return await asyncio.to_thread(_kokoro_english, text, settings)
    try:
        return await _edge_tts(text, EDGE_HI_VOICE)
    except Exception:
        return await asyncio.to_thread(_kokoro_english, text, settings)


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
