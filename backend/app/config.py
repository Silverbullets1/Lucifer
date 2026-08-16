"""Lucifer backend configuration (env-driven, .env or env vars)."""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load .env EXPLICITLY by absolute path, BEFORE Settings() is built, so the
# env vars are present regardless of cwd (systemd sets WorkingDirectory but
# python-dotenv's find_dotenv() can miss backend/.env from the app/ subdir).
# Without this the service silently falls back to the hardcoded defaults
# (e.g. wrong brain model) instead of the tuned .env values.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"  # backend/.env
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=True)
else:  # fall back to conventional search if layout ever changes
    load_dotenv(override=True)


class Settings(BaseModel):
    host: str = Field(default=os.getenv("LUCIFER_HOST", "0.0.0.0"))
    port: int = Field(default=int(os.getenv("LUCIFER_PORT", "8000")))
    # BRAIN = upstage/solar-pro4:free via Nous Portal (no Ollama). Free, FAST
    # (~4.5s, Hindi-native), unlike tencent/hy3:free which took 11-21s and
    # often returned empty content (it's a slow reasoning model).
    model: str = Field(default=os.getenv("LUCIFER_MODEL", "upstage/solar-pro4:free"))
    # Optional override if you ever self-host a different OpenAI-compatible brain.
    brain_base_url: str = Field(default=os.getenv("LUCIFER_BRAIN_BASE", ""))
    brain_api_key: str = Field(default=os.getenv("LUCIFER_BRAIN_KEY", ""))
    # STT / TTS
    device: str = Field(default=os.getenv("LUCIFER_DEVICE", "cpu"))  # cpu | cuda
    stt_model: str = Field(default=os.getenv("STT_MODEL", "base"))    # tiny|base|small
    # TTS VOICE POLICY (per SAM): Hinglish/Hindi via en-IN-PrabhatNeural (Edge TTS, male).
    # No English/USA-accent voice anywhere. tts_voice_hi kept only as offline
    # fallback (Kokoro English-India) if Edge TTS fails.
    tts_voice_hi: str = Field(default=os.getenv("TTS_VOICE_HI", "hm_psi"))
    # CORS (allow Flutter dev + Vercel frontend + local clients)
    cors_origins: list[str] = Field(default_factory=lambda: [
        o for o in (os.getenv("CORS_ORIGINS") or "*").split(",") if o
    ])
    # How many recent turns to keep in working memory per session
    memory_turns: int = Field(default=int(os.getenv("MEMORY_TURNS", "12")))


settings = Settings()
