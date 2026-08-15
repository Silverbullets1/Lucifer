"""Speech-to-Text for Lucifer voice assistant.

STT strategy (per SAM, reinforced Aug 2026):
  PRIMARY  : Nous whisper API (free, cloud — accurate multilingual Hinglish)
  FALLBACK : local faster-whisper (offline if no internet/Nous token)

Both produce plain Roman/Hindi text — no Arabic script leaks.
"""
from __future__ import annotations
import io, logging, os
from .config import Settings

log = logging.getLogger("lucifer.stt")
_model = None
_model_name = None

def _resolve_nous_creds() -> tuple[str, str] | None:
    """Try Nous JWT from auth.json or env; return (base_url, api_key) or None."""
    try:
        import json as _json
        from pathlib import Path
        auth_path = Path.home() / ".hermes" / "auth.json"
        if auth_path.exists():
            data = _json.loads(auth_path.read_text())
            nous = data.get("providers", {}).get("nous", {}) or data.get("nous", {})
            token = nous.get("access_token") or nous.get("token")
            if token:
                return "https://inference-api.nousresearch.com/v1", token
    except Exception:
        pass
    # env fallback
    base = os.environ.get("NOUS_BASE_URL", "https://inference-api.nousresearch.com/v1")
    key = os.environ.get("NOUS_API_KEY") or os.environ.get("HERMES_NOUS_KEY")
    if key:
        return base, key
    return None

def _nous_whisper(audio_bytes: bytes, settings: Settings) -> str:
    """Cloud Whisper via Nous — primary STT."""
    creds = _resolve_nous_creds()
    if not creds:
        raise RuntimeError("no Nous creds")
    base, key = creds
    import httpx
    # faster-whisper WAV already produced by ffmpeg in caller; send directly
    files = {"file": ("audio.wav", audio_bytes, "audio/wav")}
    data = {"model": "whisper-1", "language": "hi"}
    r = httpx.post(
        f"{base}/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        files=files,
        data=data,
        timeout=30,
    )
    r.raise_for_status()
    import json as _json
    text = r.json().get("text", "").strip()
    log.info("STT (nous-cloud): %s", text)
    return text

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
    """STT: try Nous cloud Whisper first, local fallback second."""
    # 1) Try cloud Whisper via Nous (free, accurate, multilingual)
    try:
        return _nous_whisper(audio_bytes, settings)
    except Exception as e:
        log.warning("Nous cloud STT failed (%s); falling back to local whisper", e)

    # 2) Local faster-whisper fallback
    model = _get_model(settings)
    import tempfile, os, time, random
    suffix = f"_{session_id}_{int(time.time()*1000)}_{random.randint(1000,9999)}.wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        path = f.name
    try:
        segments, _ = model.transcribe(path, language="hi", beam_size=5)
        result = "".join(seg.text for seg in segments).strip()
        log.info("STT (local): %s", result)
        return result
    finally:
        os.unlink(path)
