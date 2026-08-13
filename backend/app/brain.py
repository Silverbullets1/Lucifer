"""
Lucifer BRAIN — LLM wrapper around Ollama with the Lucifer persona injected.
The persona text lives in PERSONA.md (same voice as the Hermes lucifer-persona skill).
"""
from __future__ import annotations
import logging, pathlib
from typing import List, Dict
import httpx

from .config import Settings

log = logging.getLogger("lucifer.brain")

PERSONA_PATH = pathlib.Path(__file__).parent / "PERSONA.md"
PERSONA = PERSONA_PATH.read_text(encoding="utf-8") if PERSONA_PATH.exists() else "You are Lucifer."


class LuciferBrain:
    def __init__(self, settings: Settings):
        self.s = settings
        self.sys_prompt = PERSONA
        log.info("Lucifer brain ready (model=%s)", self.s.ollama_model)

    async def reply(self, user_text: str, history: List[Dict] | None = None) -> str:
        messages = [{"role": "system", "content": self.sys_prompt}]
        for turn in (history or [])[-self.s.memory_turns:]:
            messages.append(turn)
        messages.append({"role": "user", "content": user_text})

        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{self.s.ollama_base}/api/chat",
                json={
                    "model": self.s.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.85, "num_ctx": 8192},
                },
            )
            r.raise_for_status()
            data = r.json()
        return data["message"]["content"].strip()
