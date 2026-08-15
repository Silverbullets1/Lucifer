"""Speech-to-Text for Lucifer voice assistant.

STT priority chain (per SAM, reinforced Aug 2026):
  1. Groq Whisper API (free tier, cloud, accurate)
  2. Local faster-whisper small (offline fallback)
"""
from __future__ import annotations
import io, logging, os
from .config import Settings

log = logging.getLogger("lucifer.stt")
_model = None
_model_name = None


def _groq_whisper(audio_bytes: bytes, settings: Settings) -> str | None:
    """Groq Whisper API — fast, accurate, free tier."""
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    
    import httpx
    try:
        with httpx.Client(timeout=30) as client:
            r = client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                files={"file": ("voice.wav", audio_bytes, "audio/wav")},
                data={"model": "whisper-large-v3", "language": "hi"},
            )
            if r.status_code == 200:
                text = r.json().get("text", "").strip()
                log.info("STT (groq): %s", text[:60])
                return text if text else None
            log.warning("Groq STT HTTP %s: %s", r.status_code, r.text[:100])
    except Exception as e:
        log.warning("Groq STT failed: %s", e)
    return None


def _get_model(settings: Settings):
    global _model, _model_name
    want = settings.stt_model
    if _model is None or _model_name != want:
        from faster_whisper import WhisperModel
        _model = None
        _model = WhisperModel(want, device=settings.device, compute_type="int8")
        _model_name = want
    return _model


def transcribe(audio_bytes: bytes, settings: Settings, session_id: str = "default") -> str:
    """STT: Groq Whisper API first, local fallback."""
    # 1) Groq Whisper API (cloud, accurate)
    text = _groq_whisper(audio_bytes, settings)
    if text:
        return text
    
    # 2) Local faster-whisper fallback
    log.info("Groq unavailable, falling back to local whisper (%s)", settings.stt_model)
    model = _get_model(settings)
    import tempfile, time, random
    suffix = f"_{session_id}_{int(time.time()*1000)}_{random.randint(1000,9999)}.wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        path = f.name
    try:
        segments, _ = model.transcribe(path, language="hi", beam_size=5)
        result = "".join(seg.text for seg in segments).strip()
        log.info("STT (local): %s", result[:60])
        return result
    finally:
        import os
        os.unlink(path)
