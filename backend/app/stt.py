"""Speech-to-Text via faster-whisper (local, free, lifetime — no API/credit).

Primary model: settings.stt_model (default 'small' — best Hinglish accuracy on CPU).
Fallback: 'base' if small fails, for speed.
"""
from __future__ import annotations
import logging, tempfile, os, subprocess
from .config import Settings

log = logging.getLogger("lucifer.stt")
_models: dict = {}


def _to_wav(audio_bytes: bytes, suffix: str = ".webm") -> str:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        path = f.name
    wav_path = path.rsplit(".", 1)[0] + ".wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", path, "-ar", "16000", "-ac", "1", wav_path],
        capture_output=True, timeout=30,
    )
    os.unlink(path)
    return wav_path


def _get_model(name: str):
    if name not in _models:
        from faster_whisper import WhisperModel
        _models[name] = WhisperModel(name, device="cpu", compute_type="int8")
    return _models[name]


def _run(model_name: str, wav_path: str) -> str:
    model = _get_model(model_name)
    segments, _ = model.transcribe(wav_path, beam_size=5)
    return "".join(seg.text for seg in segments).strip()


def transcribe(audio_bytes: bytes, settings: Settings) -> str:
    wav_path = _to_wav(audio_bytes)
    try:
        # Primary: configured model (small = accurate Hinglish, free)
        txt = _run(settings.stt_model, wav_path)
        if txt:
            return txt
    except Exception as e:
        log.warning("STT primary (%s) failed: %s", settings.stt_model, e)
    # Fallback: base (fast, low accuracy)
    try:
        return _run("base", wav_path)
    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)
