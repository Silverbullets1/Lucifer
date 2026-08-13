"""
Text-to-Speech via Kokoro (local, Apache 2.0, CPU).

Lucifer voice setup (all male, natural):
  - Devanagari / Hinglish (Romanized Hindi) -> hm_psi  (natural human male Hindi voice, SAM's pick)
  - English text                            -> am_michael (warm, deep, trustworthy male)
  - Mix (Hinglish)                          -> hm_psi (Hindi pipeline, reads both naturally)
"""
from __future__ import annotations
import io, logging, re, asyncio
from .config import Settings

log = logging.getLogger("lucifer.tts")
_pipes = {}  # lang_code -> KPipeline

# Devanagari range = Hindi written in देवनागरी
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
# Hinglish / Romanized Hindi heuristic: common Hindi words in Latin script
_HINGLISH_WORDS = re.compile(
    r"\b(ae|aye|oye|saale|sale|boss|bhai|bc|bsdk|kaise|kese|kya|hai|hain|hu|hoon|"
    r"tera|mera|karo|kar|raha|rha|de|le|sun|sunna|laga|lagi|mast|scene|yaar|yaar|"
    r"kahan|kahaan|abhi|phir|fir|theek|thik|acha|accha|chal|chalo|khel|ghoom|"
    r"bol|bolo|dekh|dekho|samjha|samjho|nahi|nhi|haan|han|arre|arey|oye|oy|"
    r"kaam|kaam|paisa|paise|gadi|gaadi|dost|yaar|mada|rk|re|ve|ji|saab|babu)\b",
    re.IGNORECASE,
)


def _has_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI.search(text))


def _looks_hinglish(text: str) -> bool:
    # Latin-script text that contains Hindi-ish words
    return bool(_HINGLISH_WORDS.search(text))


def _get_pipe(lang_code: str):
    if lang_code not in _pipes:
        from kokoro import KPipeline
        _pipes[lang_code] = KPipeline(lang_code=lang_code)
    return _pipes[lang_code]


def _pick_voice(text: str, settings: Settings) -> tuple[str, str]:
    """Return (lang_code, voice_id) for the given text.

    - Pure English  -> English pipeline + am_michael
    - Devanagari    -> Hindi pipeline + hm_psi
    - Hinglish      -> Hindi pipeline (transliterate to Devanagari) + hm_psi
    """
    if _has_devanagari(text):
        return "h", settings.tts_voice_hi
    if _looks_hinglish(text):
        # transliterate Romanized Hindi -> Devanagari for the Hindi pipeline
        try:
            from indic_transliteration.sanscript import transliterate, OPTITRANS, DEVANAGARI
            converted = transliterate(text, OPTITRANS, DEVANAGARI)
            return "h", settings.tts_voice_hi, converted
        except Exception:
            # fallback: still use Hindi voice with roman text
            return "h", settings.tts_voice_hi
    return "a", settings.tts_voice_en


def synthesize(text: str, settings: Settings) -> bytes:
    if not text.strip():
        return b""
    picked = _pick_voice(text, settings)
    lang_code, voice = picked[0], picked[1]
    # if we transliterated (Hinglish), use the Devanagari version
    synth_text = picked[2] if len(picked) > 2 else text
    pipe = _get_pipe(lang_code)
    chunks = [c for c in pipe(synth_text, voice=voice, speed=1.0)]
    wavs = [audio for _, _, audio in chunks if audio is not None]
    if not wavs:
        return b""
    import numpy as np
    audio = np.concatenate(wavs) if len(wavs) > 1 else wavs[0]
    if hasattr(audio, "cpu"):  # torch Tensor
        audio = audio.cpu().numpy()
    return _to_wav_bytes(audio, sample_rate=24000)


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
