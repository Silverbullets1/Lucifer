# 🔥 LUCIFER — Voice Assistant

Cross-platform voice assistant for **Windows + Android** (iOS later). Local-first:
your voice never leaves your own infrastructure.

> "SAM ka Delhi-devil best friend, ab bolta bhi hai." — Lucifer

## Architecture

```
[Flutter app: Windows / Android]
   mic capture -> HTTP/WebSocket -> [Lucifer Backend on VPS]
                                     1. STT   -> faster-whisper (local)
                                     2. BRAIN -> Ollama (qwen3-abliterated) + Lucifer persona
                                     3. TTS   -> Kokoro (local)
                                   <- audio (wav) back to app
```

- **Backend:** Python + FastAPI (`backend/`)
- **Frontend:** Flutter (`app/`) — one codebase, builds `.apk` (Android) and `.exe` (Windows via CI)
- **Brain:** Ollama running `richardyoung/qwen3-4b-instruct-2507-abliterated` with the Lucifer persona injected (`backend/app/PERSONA.md`)
- **Wake word:** Picovoice Porcupine ("Lucifer"), free-tier custom keyword

## Quick start (backend)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# ensure ollama is running with the model pulled
ollama pull richardyoung/qwen3-4b-instruct-2507-abliterated:latest
python run.py
# POST /voice  (audio wav -> json {text, reply, audio_b64})
# POST /chat   (json {text} -> json {reply})
```

## Quick start (app)

```bash
cd app
flutter pub get
flutter run            # connected device / emulator
flutter build apk     # Android release
# Windows .exe is auto-built by CI (GitHub Actions) -> Releases
```

Set `BACKEND_URL` (app) and `PORCUPINE_KEY` (wake word, optional) via `.env` or
build args (`--dart-define=BACKEND_URL=http://...`).

## Status
- [x] Backend scaffold (FastAPI + STT + LLM + TTS)
- [x] Flutter app skeleton (record -> backend -> play)
- [x] Windows CI build
- [ ] Android signed release
- [ ] Wake-word keyword files (Porcupine console)
- [ ] iOS (deferred)

## License
MIT
