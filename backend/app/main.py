"""
LUCIFER — Voice Assistant Backend
FastAPI server that wires the 3-layer voice pipeline:
  Mic audio (from Flutter app) -> STT (faster-whisper)
                          -> LLM (tencent/hy3:free via Nous, + Lucifer persona)
                          -> TTS (Kokoro) -> audio back to app
Cross-platform: same backend serves Windows + Android Flutter clients.

BRAIN = tencent/hy3:free (Nous Portal). No Ollama. Free, reasoning model.
"""
from __future__ import annotations
import os, io, logging, asyncio, tempfile, base64
from pathlib import Path
from typing import AsyncGenerator
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel

load_dotenv()
from .config import settings
from .brain import reply as brain_reply, stream_reply as brain_stream
from .stt import transcribe
from .tts import synthesize

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("lucifer")

app = FastAPI(title="Lucifer Voice Assistant", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "model": settings.model, "device": settings.device}


@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html><html><head><meta charset="utf-8">
    <title>LUCIFER — Online</title>
    <style>body{background:#05060a;color:#ff2d55;font-family:monospace;
    display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
    .box{text-align:center}.glow{font-size:3rem;text-shadow:0 0 20px #ff2d55}
    .sub{color:#7b2dff;margin-top:1rem}.tag{color:#00e5ff}</style></head>
    <body><div class="box"><div class="glow">🔥 LUCIFER</div>
    <div class="sub">Voice Assistant backend is <span class="tag">ONLINE</span></div>
    <div class="sub">Brain: tencent/hy3:free · TTS: Kokoro (male)</div></div></body></html>
    """


class ChatReq(BaseModel):
    text: str
    history: list[dict] | None = None


@app.post("/chat")
async def chat(req: ChatReq):
    """Text-in -> text-out (used for quick testing / non-voice mode)."""
    try:
        reply = await brain_reply(req.text, req.history or [])
    except Exception as e:
        log.exception("chat failed")
        raise HTTPException(500, str(e))
    return {"reply": reply}


@app.post("/chat/stream")
async def chat_stream(req: ChatReq):
    """Stream the Lucifer reply token-by-token (premium low-latency feel)."""
    async def gen():
        try:
            async for tok in brain_stream(req.text, req.history or []):
                yield tok
        except Exception as e:
            log.exception("stream failed")
            yield f"[error: {e}]"
    return StreamingResponse(gen(), media_type="text/plain")


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
        reply = await brain_reply(text)
    except Exception as e:
        log.exception("llm failed")
        raise HTTPException(500, f"llm: {e}")
    log.info("LUCIFER: %s", reply)
    # 3) TTS
    try:
        wav_bytes = await synthesize(reply, settings)
    except Exception as e:
        log.exception("tts failed")
        return {"text": text, "reply": reply, "audio_b64": ""}
    return {"text": text, "reply": reply, "audio_b64": base64.b64encode(wav_bytes).decode()}


@app.post("/tts")
async def tts(req: ChatReq):
    """Text-in -> TTS audio (wav bytes). Used by the web frontend to speak replies."""
    try:
        wav_bytes = await synthesize(req.text, settings)
    except Exception as e:
        log.exception("tts failed")
        raise HTTPException(500, f"tts: {e}")
    return StreamingResponse(io.BytesIO(wav_bytes), media_type="audio/wav")


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
            reply = await brain_reply(text)
            await ws.send_json({"type": "llm", "text": reply})
            wav = await synthesize(reply, settings)
            await ws.send_bytes(wav)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("ws error")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
