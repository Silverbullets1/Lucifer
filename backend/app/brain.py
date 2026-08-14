"""
Lucifer BRAIN — calls tencent/hy3:free (Nous Portal) directly.
No Ollama. Uses the same Nous inference JWT the Hermes gateway already
holds in ~/.hermes/auth.json, so it's free and needs no extra key.

tencent/hy3:free is a *reasoning* model: it streams a `reasoning` field
then the actual `content`. We read both; the assistant reply is `content`.
"""
from __future__ import annotations
import json, logging, os, sys, re, subprocess, asyncio, shlex
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
    # Auto-load verified facts (sources of truth for current affairs; > training memory).
    fb = base / "FACTS.md"
    if fb.exists():
        persona += (
            "\n\n--- VERIFIED FACTS (trust this OVER your training memory) ---\n"
            + fb.read_text(encoding="utf-8")
        )
    return persona


# --- Live web search trigger words (English + Hindi + Hinglish) ---
# Per spec: trigger ONLY on real-time / current / time-sensitive topics.
# Bare question words (who/what/kaun/kya) do NOT trigger by themselves.
_WEB_TRIGGERS = re.compile(
    r"\b(?:"
    # time & freshness
    r"latest|newest|new|current|now|today|tonight|tomorrow|yesterday|"
    r"this\s+morning|this\s+afternoon|this\s+evening|this\s+week|this\s+month|this\s+year|"
    r"recently|recent|updated?|live|breaking|trending|ongoing|"
    r"aaj(?:\s+ka|\s+ki)?|abhi(?:\s+ka|\s+tak|\s+abhi)?|filhal|is\s+wakt|iss\s+time|"
    r"kal|parso|is\s+hafte|iss\s+week|is\s+mahine|iss\s+month|is\s+saal|iss\s+year|"
    r"nay(?:a|e|i)|fresh|taza(?:r?|khabar)?|"
    # information lookup
    r"news|announcement|official|docs?|documentation|release|launch|changelog|roadmap|"
    r"version|patch|api|khabar|adhikarik|document|"
    # finance & shopping
    r"price|cost|discount|sale|offer|stock\s+price|market|crypto|bitcoin|exchange\s+rate|"
    r"daam|kimat|keemat|kitne\s+ka|kitni\s+ki|share\s+price|rate|"
    # sports & events
    r"score|result|match(?:\s+ka\s+result)?|fixture|schedule|standings|ranking|"
    r"tournament|live\s+score|natija|kab\s+hai|"
    # weather & time
    r"weather|forecast|temperature|rain|time|date|timezone|"
    r"mausam|barish|garmi|thand|taapmaan|samay|tareekh|"
    # technology
    r"github|repository|repo|package|npm|pip|sdk|framework|library|model|ai\s+model|"
    # government & public info
    r"election|policy|law|notification|vacancy|admit\s+card|exam\s+result|"
    r"chunav|kanoon|bharti|sarkari"
    r")\b",
    re.I,
)


def _ddg_instant(q: str) -> str:
    try:
        import urllib.parse
        url = ("https://api.duckduckgo.com/?q=" + urllib.parse.quote(q)
               + "&format=json&no_html=1&skip_disambig=1")
        out = subprocess.run(
            ["curl", "-s", "--max-time", "6", url],
            capture_output=True, text=True, timeout=8,
        ).stdout
        if not out.strip():
            return ""
        d = json.loads(out)
        ans = (d.get("AbstractText") or "").strip()
        if ans:
            return ans
        for t in d.get("RelatedTopics", [])[:3]:
            if isinstance(t, dict) and t.get("Text"):
                return t["Text"]
    except Exception as e:
        log.warning("web_fact ddg failed: %s", e)
    return ""


def _wiki_search(q: str) -> str:
    try:
        out = subprocess.run(
            ["curl", "-s", "--max-time", "6",
             f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch="
             f"{shlex.quote(q)}&format=json&srlimit=1"],
            capture_output=True, text=True, timeout=8,
        ).stdout
        d = json.loads(out)
        hits = d.get("query", {}).get("search", [])
        if hits:
            snip = re.sub(r"<[^>]+>", "", hits[0].get("snippet", ""))
            return snip
    except Exception as e:
        log.warning("web_fact wiki failed: %s", e)
    return ""


def _firecrawl_search(q: str, settings=None) -> str:
    """Nous Tool Gateway -> Firecrawl (FREE, key-less). 3rd-tier web fallback
    after DuckDuckGo + Wikipedia. Agent-grade search + full-page extraction.
    Uses the gateway /v2/search endpoint (no extra SDK needed)."""
    try:
        import json
        import urllib.request
        from pathlib import Path
        home = (settings.hermes_home if settings else os.path.expanduser("~/.hermes"))
        auth = Path(home) / "auth.json"
        if not auth.is_file():
            return ""
        data = json.loads(auth.read_text(encoding="utf-8-sig"))
        nous = (data.get("providers") or {}).get("nous") or {}
        token = nous.get("access_token")
        if not token:
            return ""
        domain = (settings.nous_gateway_domain if settings else "nousresearch.com")
        scheme = (settings.nous_gateway_scheme if settings else "https")
        origin = f"{scheme}://firecrawl-gateway.{domain}"
        url = f"{origin}/v2/search"
        body = json.dumps({"query": q, "limit": 3, "origin": "lucifer-bot"}).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read())
        # Firecrawl v2: {"success":true,"data":{"web":[{url,title,description}]}}
        data = resp.get("data") or {}
        items = data.get("web") or []
        if not items and isinstance(data, list):
            items = data
        for it in items[:3]:
            if isinstance(it, dict):
                txt = (it.get("description") or it.get("markdown") or it.get("content")
                       or it.get("snippet") or it.get("text") or "").strip()
                if txt:
                    return txt[:1200]
            elif isinstance(it, str) and it.strip():
                return it.strip()[:1200]
    except Exception as e:
        log.warning("web_fact firecrawl failed: %s", e)
    return ""


def web_fact(query: str, settings=None) -> str:
    """Live web lookup for GK / current-affairs questions. Returns text or ''.
    Order: Firecrawl/Nous (1st, FREE + reliable) -> DuckDuckGo (2nd) -> Wikipedia (3rd)."""
    q = query.strip()
    ans = _firecrawl_search(q, settings)
    if not ans:
        ans = _ddg_instant(q)
    if not ans:
        ans = _wiki_search(q)
    return ans


# Question words (who/what/kaun/kya...): per revised rule these DO trigger
# web search — factual questions need live data. Self-reference is excluded so
# the bot doesn't "search the web" about itself.
_QUESTION_WORDS = re.compile(
    r"\b(?:who|what|which|when|where|why|how|whom|whose|"
    r"kaun|kaunsa|kaunsi|kya|kab|kahan|kahaan|kyun|kaise|"
    r"kitna|kitni|kitne|kitne din|kitni der)\b",
    re.I,
)
_SELF_REF = re.compile(
    r"\b(?:tu|tum|tumhara|tumhari|you|your|yourself|"
    r"lucifer|devil|apna|apni|main|mein|i am|mera|meri)\b",
    re.I,
)


def needs_web(user_text: str) -> bool:
    """Web search triggers on: (a) any time-sensitive / topic trigger word, OR
    (b) a question word about something other than the bot itself."""
    if _WEB_TRIGGERS.search(user_text):
        return True
    if _QUESTION_WORDS.search(user_text) and not _SELF_REF.search(user_text):
        return True
    return False


async def reply(user_text: str, history=None) -> str:
    """One-shot reply (non-streaming)."""
    api_key, base = _resolve_creds()
    persona = _load_persona()
    messages = [{"role": "system", "content": persona}]

    # Live web lookup for real-time / current-affairs questions.
    web_ctx = ""
    if needs_web(user_text):
        fact = await asyncio.to_thread(web_fact, user_text)
        if fact:
            web_ctx = (
                f"\n\n--- LIVE WEB FACT (verified just now via web search, "
                f"trust this over memory) ---\n{fact}\n"
            )
        else:
            web_ctx = (
                "\n\n--- WEB SEARCH ATTEMPTED, NO LIVE RESULT ---\n"
                "You tried to fetch live/current info but got nothing. "
                "Do NOT guess time-sensitive facts. Tell the user (in Hinglish) "
                "you couldn't pull live info right now.\n"
            )
        messages[0]["content"] += web_ctx

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

    # Live web lookup for real-time / current-affairs questions.
    if needs_web(user_text):
        fact = await asyncio.to_thread(web_fact, user_text)
        if fact:
            messages[0]["content"] += (
                f"\n\n--- LIVE WEB FACT (verified just now via web search, "
                f"trust this over memory) ---\n{fact}\n"
            )
        else:
            messages[0]["content"] += (
                "\n\n--- WEB SEARCH ATTEMPTED, NO LIVE RESULT ---\n"
                "You tried to fetch live/current info but got nothing. "
                "Do NOT guess time-sensitive facts. Tell the user (in Hinglish) "
                "you couldn't pull live info right now.\n"
            )

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
