"""Lucifer backend configuration (env-driven, .env or env vars)."""
from __future__ import annotations
import os
from pathlib import Path

# Load .env from the backend dir (where run.py lives) so SARVAM_API_KEY etc.
# are available without exporting them into the shell.
try:
    from dotenv import load_dotenv
    _env = Path(__file__).resolve().parent.parent / ".env"
    if _env.exists():
        load_dotenv(_env)
except Exception:  # dotenv optional; env vars may already be set
    pass

from pydantic import BaseModel, Field


class Settings(BaseModel):
    host: str = Field(default=os.getenv("LUCIFER_HOST", "0.0.0.0"))
    port: int = Field(default=int(os.getenv("LUCIFER_PORT", "8723")))
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
    # TTS VOICE POLICY (per SAM): ONLY Hindi/Hinglish.
    # Primary: Sarvam Bulbul V3 — Kabir (Indian MALE, native Hinglish code-switching).
    # Fallback: Edge TTS Prabhat (Indian MALE, Hinglish) if Sarvam fails.
    # tts_voice_hi kept only as offline fallback (Kokoro Hindi) if both cloud TTS fail.
    tts_voice_hi: str = Field(default=os.getenv("TTS_VOICE_HI", "hm_psi"))
    sarvam_api_key: str = Field(default=os.getenv("SARVAM_API_KEY", ""))
    sarvam_speaker: str = Field(default=os.getenv("SARVAM_SPEAKER", "kabir"))
    edge_hi_voice: str = Field(default=os.getenv("EDGE_HI_VOICE", "en-IN-PrabhatNeural"))
    # CORS (allow Flutter dev + Vercel frontend + local clients)
    cors_origins: list[str] = Field(default_factory=lambda: [
        o for o in (os.getenv("CORS_ORIGINS") or "*").split(",") if o
    ])
    # How many recent turns to keep in working memory per session
    memory_turns: int = Field(default=int(os.getenv("MEMORY_TURNS", "12")))


settings = Settings()
