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
    import tempfile, os, subprocess
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(audio_bytes)
        path = f.name
    wav_path = path.replace(".webm", ".wav")
    try:
        # Convert to 16kHz mono wav (whisper's preferred, avoids decode errors)
        subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-ar", "16000", "-ac", "1", wav_path],
            capture_output=True, timeout=30,
        )
        model = _get_model(settings)
        segments, _ = model.transcribe(wav_path, language="en", beam_size=5)
        return "".join(seg.text for seg in segments).strip()
    finally:
        os.unlink(path)
        if os.path.exists(wav_path):
            os.unlink(wav_path)
