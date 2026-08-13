"""
Run the Lucifer backend.

Local dev:
    python -m app.main
Then hit:
    POST /voice  (audio file -> json {text, reply, audio_b64})
    POST /chat   (json {text}  -> json {reply})
    WS   /ws     (audio stream <-> audio stream)
"""
import uvicorn
from app.config import settings

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
