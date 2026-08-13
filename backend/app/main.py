"""
LUCIFER — Voice Assistant Backend
FastAPI server that wires the 3-layer voice pipeline:
  Mic audio (from Flutter app) -> STT (faster-whisper)
                          -> LLM (Ollama + Lucifer persona)
                          -> TTS (Kokoro) -> audio back to app
Cross-platform: same backend serves Windows + Android Flutter clients.
"""
from __future__ import annotations
import os, io, logging, asyncio, tempfile
from pathlib import Path
from typing import AsyncGenerator
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()
from .config import Settings
from .brain import LuciferBrain
from .stt import transcribe
from .tts import synthesize

settings = Settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("lucifer")

app = FastAPI(title="Lucifer Voice Assistant", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"], allow_headers=["*"],
)

# Lazily-built singletons
_brain: LuciferBrain | None = None
def brain() -> LuciferBrain:
    global _brain
    if _brain is None:
        _brain = LuciferBrain(settings)
    return _brain


@app.get("/health")
async def health():
    return {"status": "ok", "model": settings.ollama_model, "device": settings.device}


class ChatReq(BaseModel):
    text: str
    history: list[dict] | None = None


@app.post("/chat")
async def chat(req: ChatReq):
    """Text-in -> text-out (used for quick testing / non-voice mode)."""
    try:
        reply = await brain().reply(req.text, req.history or [])
    except Exception as e:
        log.exception("chat failed")
        raise HTTPException(500, str(e))
    return {"reply": reply}


@app.post("/voice")
async def voice(audio: UploadFile = File(...)):
    """Voice-in: audio file -> STT -> LLM -> TTS audio (wav bytes)."""
    data = await audio.read()
    if not data:
        raise HTTPException(400, "empty audio")
    # 1) STT
    try:
        text = transcribe(data, settings)
    except Exception as e:
        log.exception("stt failed")
        raise HTTPException(500, f"stt: {e}")
    log.info("USER: %s", text)
    if not text.strip():
        return {"text": "", "reply": "", "audio_b64": ""}
    # 2) LLM
    try:
        reply = await brain().reply(text)
    except Exception as e:
        log.exception("llm failed")
        raise HTTPException(500, f"llm: {e}")
    log.info("LUCIFER: %s", reply)
    # 3) TTS
    try:
        wav_bytes = synthesize(reply, settings)
    except Exception as e:
        log.exception("tts failed")
        # still return text if tts fails
        return {"text": text, "reply": reply, "audio_b64": ""}
    import base64
    return {"text": text, "reply": reply, "audio_b64": base64.b64encode(wav_bytes).decode()}


@app.websocket("/ws")
async def ws(ws: WebSocket):
    """Streaming voice loop: client sends audio chunks, server replies audio."""
    await ws.accept()
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            data = msg.get("bytes") or msg.get("text")
            if isinstance(data, str):
                data = data.encode()
            if not data:
                continue
            text = transcribe(data, settings)
            await ws.send_json({"type": "stt", "text": text})
            if not text.strip():
                continue
            reply = await brain().reply(text)
            await ws.send_json({"type": "llm", "text": reply})
            wav = synthesize(reply, settings)
            await ws.send_bytes(wav)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("ws error")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
