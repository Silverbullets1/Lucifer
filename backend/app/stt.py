"""Speech-to-Text via faster-whisper (local, no cloud)."""
from __future__ import annotations
import io, logging
from .config import Settings

log = logging.getLogger("lucifer.stt")
_model = None


def _get_model(settings: Settings):
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(settings.stt_model, device=settings.device, compute_type="int8")
    return _model


def transcribe(audio_bytes: bytes, settings: Settings) -> str:
    model = _get_model(settings)
    # faster-whisper accepts a path or file-like; write to temp for safety
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        path = f.name
    try:
        segments, _ = model.transcribe(path, language=None, beam_size=5)
        return "".join(seg.text for seg in segments).strip()
    finally:
        os.unlink(path)
