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

import re as _re

# Reply sanitizer: strip emoji (TTS can't speak them) — persona also forbids
# emoji/markdown, this is a safety net so nothing slips through to speech.
_EMOJI_RE = _re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF\U0000FE00-\U0000FE0F"
    "\U0000200D\U00002702-\U000027B0]+", flags=_re.UNICODE)

# --- HINGLISH WORD-SPLITTER -------------------------------------------------
# upstage free model often GLUES Roman-Hindi words together (hellojaan,
# kaisehotum). We greedily re-segment glued tokens using a known-word
# dictionary so the reply reads naturally and TTS doesn't mangle it.
_HINGLISH_WORDS = set("""
hello hi hey hellow hlo jaan jan raja king sher sona babu sweetheart sam my
kaise kaisi kaisa ho hai hain hoon hun the thi tha bhi to aur ek do teen chaar
paanch chhe saath aath nau das suna sunao sunaye sunayi diya de do dena batao
bata na kya haal chaal halchal chal raha rehta rehti aaj kal abhi phir wapas
thoda bahut samay time plan mast accha achha badhiya theek sahi pyaar pyar love
miss karo karto bhi re baba yaar friend dost team mera
meri mere tumhara tumhari tumhre apna apni baat baatein bol bolta bolkar soch
samajh dekh dikha aankh dil dimag khush dukh gussa sanam tum tu aap kyun kaun
kab kahan kaise kuch sab koi ye vo woh apan hum hai hote the matlab fir se aage
peeche upar niche andar bahar sath saath mein par le liye gaya gayi gaya gaya
karta karti karte karna aati aata aate jaati jaata jaate rahi raha rahe aayi aaya
aaye hui thi thi thi thi bolti boli bole aati jati jati aati bolu bolo bolna
sun lo suno sunna sun liya dekho dekhna dekhti dekhta pucho puchna puchta puchi
laga lagao lagti lagta laga lage chala chali chale chalte chalu karu karu kari
kare kaam kama karam baat baate baaten baato pyari pyare sundar suhani suhana
apne apni tumhe tumko mujhe mujhko use usko ise unko unhe hame hamko aapko
tumhari tumhare tumhari meri meri se ki ko ka ke mein par tak bhi hi to bhi
kaisi kaisa kaisi kaise kahan kahaan kabhi kabhi kabhi kabhi thoda thodi thode
bahut bahut bahut zyada kam jyada jyaada bilkul ekdam ek dum dum bhar poora puri
purana purani naya nayi gaana gana gaane gaana gane suna sunayi sunai suni sunte
pyaar mohabbat ishq dil dhadkan saans saanson jeene jina zindagi zindgi jeevan
sochte sochta sochti samjha samjho samajhna samajhti samajhta yaad yaadein
yaadon bhool bhuli bhul gayi bhul gaya bhul gaye ro rota roti rote hansee hansi
hans hansna hansti hanske rona roya royi roye muskura muskurahat muskurahat
khushi khushiyaan khush dukhi dukh takleef pareshani gussa ghussa naraz naraz
narazgi pyaar mohabbat chahta chahti chahte chahta chahna sona soti sote sota
kaam kam kar rahe ho the tum aaj kal ab subah shaam raat din savera subah
sakal sukoon aaram aaraam thakan thake thaki thake hue hue thi thi thi thi
""".split())

_MAX_WORD = 14

def _segment_token(tok: str) -> str:
    """Conservative segmentation: only split a token when the ENTIRE token
    decomposes into dictionary words (a genuinely glued compound like
    'hellojaan'). If any char can't be matched, assume the token is already a
    valid word and return it UNCHANGED — never break into single characters
    (that was destroying correctly-spelled words like 'Haan' -> 'H aa n')."""
    low = tok.lower()
    n = len(low)
    out = []
    i = 0
    while i < n:
        matched = ""
        for L in range(min(_MAX_WORD, n - i), 0, -1):
            w = low[i:i + L]
            if w in _HINGLISH_WORDS:
                matched = w
                break
        if matched:
            out.append(matched)
            i += len(matched)
        else:
            return tok  # not cleanly glued -> keep original, untouched
    if len(out) >= 2:
        return " ".join(out)
    return tok  # single dictionary word -> leave as-is

_TOKEN_RE = _re.compile(r"[A-Za-z]+")

def _fix_hinglish_spacing(text: str) -> str:
    """Re-segment glued Roman-Hindi runs while leaving punctuation/emoji alone."""
    return _TOKEN_RE.sub(lambda m: _segment_token(m.group(0)), text)

def sanitize_reply(text: str) -> str:
    if not text:
        return text
    text = _EMOJI_RE.sub("", text)              # remove all emoji (TTS safety net)
    text = _fix_hinglish_spacing(text)          # split glued words (hellojaan)
    # ensure a space after punctuation when followed by a letter
    text = _re.sub(r"([,?!;:])([A-Za-z])", r"\1 \2", text)
    text = _re.sub(r"\s{2,}", " ", text).strip()  # collapse extra spaces
    return text

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
        reply = sanitize_reply(reply)
    except Exception as e:
        log.exception("chat failed")
        raise HTTPException(500, str(e))
    return {"reply": reply}


@app.post("/chat/stream")
async def chat_stream(req: ChatReq):
    """Stream the Lucifer reply token-by-token (premium low-latency feel)."""
    async def gen():
        buffer = ""
        clean_prev = ""
        try:
            async for tok in brain_stream(req.text, req.history or []):
                buffer += tok
                # Re-sanitize the WHOLE buffer each tick so cross-token glued
                # words (model emits "Hello" then "jaan" separately) get split.
                clean = sanitize_reply(buffer)
                if len(clean) > len(clean_prev):
                    yield clean[len(clean_prev):]
                    clean_prev = clean
            # flush any trailing clean content
            final = sanitize_reply(buffer)
            if len(final) > len(clean_prev):
                yield final[len(clean_prev):]
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
    return await _handle_voice(data)


@app.get("/voice")
async def voice_get():
    """GET fallback so stale cached JS sending GET still works (returns hint)."""
    return {"text": "", "reply": "", "audio_b64": "", "note": "use POST /voice with audio"}


async def _handle_voice(data: bytes):
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
        reply = sanitize_reply(reply)
    except Exception as e:
        log.exception("llm failed")
        raise HTTPException(500, f"llm: {e}")
    log.info("LUCIFER: %s", reply)
    # 3) TTS (plain natural Hindi voice)
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
    return StreamingResponse(io.BytesIO(wav_bytes), media_type="audio/mpeg")


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
            await ws.send_json({"type": "llm", "text": sanitize_reply(reply)})
            wav = await synthesize(reply, settings)
            await ws.send_bytes(wav)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("ws error")


# --- Serve frontend from backend (single origin = mic + CORS both work) ---
_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if not _FRONTEND_DIR.exists():
    _FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent  # fallback: repo root
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

@app.get("/app")
async def frontend_app():
    # prefer /frontend dir, else repo root
    for d in (_FRONTEND_DIR, Path(__file__).resolve().parent.parent.parent):
        idx = d / "index.html"
        if idx.exists():
            return FileResponse(idx)
    return HTMLResponse("<h1>Lucifer frontend missing</h1>")

@app.get("/app.js")
async def frontend_js():
    for d in (_FRONTEND_DIR, Path(__file__).resolve().parent.parent.parent):
        js = d / "app.js"
        if js.exists():
            return FileResponse(js, media_type="application/javascript")
    return HTMLResponse("not found", status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
