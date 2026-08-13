"""Text-to-Speech via Kokoro (local, Apache 2.0, runs on CPU)."""
from __future__ import annotations
import io, logging, wave, struct, asyncio
from .config import Settings

log = logging.getLogger("lucifer.tts")
_pipe = None


def _get_pipe(settings: Settings):
    global _pipe
    if _pipe is None:
        from kokoro import KPipeline
        # en_US pipeline
        _pipe = KPipeline(lang_code="a")
    return _pipe


def synthesize(text: str, settings: Settings) -> bytes:
    if not text.strip():
        return b""
    pipe = _get_pipe(settings)
    # split long text into sentences; Kokoro handles chunks via generator
    chunks = [c for c in pipe(text, voice=settings.tts_voice, speed=1.0, split=True)]
    wavs = [audio for _, _, audio in chunks if audio is not None]
    if not wavs:
        return b""
    # Kokoro returns float32 arrays at 24kHz; concatenate and wrap as WAV
    import numpy as np
    audio = np.concatenate(wavs) if len(wavs) > 1 else wavs[0]
    return _to_wav_bytes(audio, sample_rate=24000)


def _to_wav_bytes(audio_float, sample_rate: int) -> bytes:
    import numpy as np
    audio_int = (np.clip(audio_float, -1.0, 1.0) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int.tobytes())
    return buf.getvalue()
