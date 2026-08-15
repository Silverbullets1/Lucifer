"""Speech-to-Text via faster-whisper (local, no cloud)."""
from __future__ import annotations
import io, logging
from .config import Settings

log = logging.getLogger("lucifer.stt")
_model = None
_model_name = None


def _get_model(settings: Settings):
    global _model, _model_name
    want = settings.stt_model
    if _model is None or _model_name != want:
        from faster_whisper import WhisperModel
        # release old model first to free CPU RAM on switch
        _model = None
        _model = WhisperModel(want, device=settings.device, compute_type="int8")
        _model_name = want
    return _model


def transcribe(audio_bytes: bytes, settings: Settings, session_id: str = "default") -> str:
    model = _get_model(settings)
    import tempfile, os, time, random
    # unique temp filename per session/timestamp to avoid cross-request race
    suffix = f"_{session_id}_{int(time.time()*1000)}_{random.randint(1000,9999)}.wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        path = f.name
    try:
        segments, _ = model.transcribe(path, language=None, beam_size=5)
        return "".join(seg.text for seg in segments).strip()
    finally:
        os.unlink(path)
