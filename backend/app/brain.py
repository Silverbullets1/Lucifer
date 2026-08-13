"""
Lucifer BRAIN — calls tencent/hy3:free (Nous Portal) directly.
No Ollama. Uses the same Nous inference JWT the Hermes gateway already
holds in ~/.hermes/auth.json, so it's free and needs no extra key.

tencent/hy3:free is a *reasoning* model: it streams a `reasoning` field
then the actual `content`. We read both; the assistant reply is `content`.
"""
from __future__ import annotations
import json, logging, os, sys
from pathlib import Path
from typing import AsyncIterator

import httpx
from .config import Settings

log = logging.getLogger("lucifer.brain")

_AUTH_PATH = Path.home() / ".hermes" / "auth.json"

# Hardened import: resolve_nous_runtime_credentials lives inside the
# hermes-agent package. We add it to sys.path so this module works even
# when the backend venv doesn't have hermes installed.
_HERMES_AGENT = Path("/home/ubuntu/hermes-agent")
if str(_HERMES_AGENT) not in sys.path:
    sys.path.insert(0, str(_HERMES_AGENT))


def _resolve_creds():
    try:
        from hermes_cli.auth import resolve_nous_runtime_credentials
        c = resolve_nous_runtime_credentials()
        return c["api_key"], c["base_url"].rstrip("/")
    except Exception as exc:  # pragma: no cover
        log.warning("brain: could not resolve Nous creds via hermes (%s); "
                    "falling back to HERMES_NOUS_KEY env", exc)
        key = os.environ.get("HERMES_NOUS_KEY")
        base = os.environ.get("HERMES_NOUS_BASE",
                              "https://inference-api.nousresearch.com/v1")
        if not key:
            raise RuntimeError("No Nous credentials available for Lucifer brain")
        return key, base.rstrip("/")


def _load_persona() -> str:
    """Load the active persona system prompt.

    PERSONA.md is the live persona file — drop your new TTS-friendly script
    there and it is picked up on next restart. Until then we fall back to a
    neutral default so the backend never hard-codes an old persona.
    """
    base = Path(__file__).parent
    p = base / "PERSONA.md"
    if p.exists():
        persona = p.read_text(encoding="utf-8")
    else:
        # Neutral default fallback (TTS-friendly, no hardcoded persona name).
        persona = (
            "You are a helpful, friendly voice assistant. "
            "Reply in short, natural, spoken-language sentences that sound good "
            "when read aloud by a text-to-speech engine. Keep replies concise and "
            "conversational. Avoid emoji, markup, or stage directions."
        )
    # Auto-load the self-improving slang bank (cron appends new words here).
    sb = base / "slang_bank.md"
    if sb.exists():
        persona += (
            "\n\n--- AUTO-LOADED SLANG BANK (use these words naturally in replies) ---\n"
            + sb.read_text(encoding="utf-8")
        )
    return persona


async def reply(user_text: str, history=None) -> str:
    """One-shot reply (non-streaming)."""
    api_key, base = _resolve_creds()
    persona = _load_persona()
    messages = [{"role": "system", "content": persona}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={"model": Settings().model, "messages": messages,
                  "max_tokens": 700, "temperature": 0.8},
        )
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"].get("content") or ""


async def stream_reply(user_text: str, history=None) -> AsyncIterator[str]:
    """Stream the assistant reply token-by-token (premium low-latency feel)."""
    api_key, base = _resolve_creds()
    persona = _load_persona()
    messages = [{"role": "system", "content": persona}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST", f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={"model": Settings().model, "messages": messages,
                  "max_tokens": 700, "temperature": 0.8, "stream": True},
        ) as resp:
            resp.raise_for_status()
            # SSE parse: lines "data: {...}" ; reasoning then content chunks.
            buf = ""
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                text = delta.get("content")
                if text:
                    yield text
