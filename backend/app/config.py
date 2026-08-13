"""Lucifer backend configuration (env-driven, .env or env vars)."""
from __future__ import annotations
import os
from pydantic import BaseModel, Field


class Settings(BaseModel):
    host: str = Field(default=os.getenv("LUCIFER_HOST", "0.0.0.0"))
    port: int = Field(default=int(os.getenv("LUCIFER_PORT", "8723")))
    # BRAIN = tencent/hy3:free via Nous Portal (no Ollama). Free, reasoning model.
    model: str = Field(default=os.getenv("LUCIFER_MODEL", "tencent/hy3:free"))
    # Optional override if you ever self-host a different OpenAI-compatible brain.
    brain_base_url: str = Field(default=os.getenv("LUCIFER_BRAIN_BASE", ""))
    brain_api_key: str = Field(default=os.getenv("LUCIFER_BRAIN_KEY", ""))
    # STT / TTS
    device: str = Field(default=os.getenv("LUCIFER_DEVICE", "cpu"))  # cpu | cuda
    stt_model: str = Field(default=os.getenv("STT_MODEL", "base"))    # tiny|base|small
    tts_voice: str = Field(default=os.getenv("TTS_VOICE", "af_heart"))  # Kokoro voice id
    # CORS (allow Flutter dev + local clients)
    cors_origins: list[str] = Field(default_factory=lambda: [
        o for o in (os.getenv("CORS_ORIGINS") or "http://localhost,http://127.0.0.1").split(",") if o
    ])
    # How many recent turns to keep in working memory per session
    memory_turns: int = Field(default=int(os.getenv("MEMORY_TURNS", "12")))


settings = Settings()
