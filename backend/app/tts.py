"""
Text-to-Speech via Kokoro (local, Apache 2.0, CPU).

Lucifer voice setup (all male, natural):
  - Hindi / Hinglish text (Devanagari detected) -> hm_omega  (natural human male)
  - English text                               -> am_michael (warm, deep, trustworthy male)
"""
from __future__ import annotations
import io, logging, re, asyncio
from .config import Settings

log = logging.getLogger("lucifer.tts")
_pipes = {}  # lang_code -> KPipeline


def _get_pipe(lang_code: str):
    if lang_code not in _pipes:
        from kokoro import KPipeline
        _pipes[lang_code] = KPipeline(lang_code=lang_code)
    return _pipes[lang_code]


# Devanagari range = Hindi / Hinglish
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")


def _pick_voice(text: str, settings: Settings) -> tuple[str, str]:
    """Return (lang_code, voice_id) for the given text."""
    if _DEVANAGARI.search(text):
        return "h", settings.tts_voice_hi   # Hindi pipeline + hm_omega
    return "a", settings.tts_voice_en        # English pipeline + am_michael


def synthesize(text: str, settings: Settings) -> bytes:
    if not text.strip():
        return b""
    lang_code, voice = _pick_voice(text, settings)
    pipe = _get_pipe(lang_code)
    chunks = [c for c in pipe(text, voice=voice, speed=1.0)]
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
