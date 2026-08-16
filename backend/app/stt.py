"""Speech-to-Text for Lucifer voice assistant.

STT priority chain:
  1. Local faster-whisper small (offline, accurate, no hallucinations)
  2. Groq Whisper API (cloud backup — only if local fails)
"""
from __future__ import annotations
import io, logging, os, struct, math
import numpy as np
from .config import Settings

log = logging.getLogger("lucifer.stt")
_model = None
_model_name = None


def _noise_filter(audio_bytes: bytes) -> bytes:
    """Apply noise gate + normalize + DC offset removal to raw 16-bit PCM WAV."""
    try:
        import wave
        wav = io.BytesIO(audio_bytes)
        with wave.open(wav, 'rb') as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        if sampwidth != 2:
            return audio_bytes

        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)

        if n_channels == 2:
            samples = samples[::2]

        # DC offset removal
        samples = samples - np.mean(samples)

        # Noise gate
        threshold = np.max(np.abs(samples)) * 0.02
        gated = np.where(np.abs(samples) > threshold, samples, 0)

        # Normalize
        peak = np.max(np.abs(gated))
        if peak > 0:
            gated = (gated / peak) * 26000

        clean = gated.astype(np.int16)

        out = io.BytesIO()
        with wave.open(out, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(framerate)
            wf.writeframes(clean.tobytes())

        return out.getvalue()
    except Exception as e:
        log.warning("Noise filter failed: %s, using raw audio", e)
        return audio_bytes


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
    """STT: Local faster-whisper small first (offline, accurate), Groq backup."""
    # Apply noise filter
    clean_audio = _noise_filter(audio_bytes)

    # 1) Local faster-whisper small (primary — no hallucinations)
    try:
        model = _get_model(settings)
        import tempfile, time, random
        suffix = f"_{session_id}_{int(time.time()*1000)}_{random.randint(1000,9999)}.wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(clean_audio)
            path = f.name
        try:
            segments, _ = model.transcribe(path, language="hi", beam_size=5)
            result = "".join(seg.text for seg in segments).strip()
            if result:
                log.info("STT (local): %s", result[:60])
                return result
        finally:
            import os
            os.unlink(path)
    except Exception as e:
        log.warning("Local STT failed: %s", e)

    # 2) Groq Whisper API (backup — only if local fails)
    key = os.environ.get("GROQ_API_KEY")
    if key:
        try:
            import httpx
            with httpx.Client(timeout=30) as client:
                r = client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {key}"},
                    files={"file": ("voice.wav", clean_audio, "audio/wav")},
                    data={"model": "whisper-large-v3", "language": "hi"},
                )
                if r.status_code == 200:
                    text = r.json().get("text", "").strip()
                    if text:
                        log.info("STT (groq): %s", text[:60])
                        return text
        except Exception as e:
            log.warning("Groq STT failed: %s", e)

    return ""
