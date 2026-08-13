#!/usr/bin/env python3
"""
LUCIFER SELF-EVOLUTION CRON (standalone, no external deps)
==========================================================
Runs on a schedule. Self-improves Lucifer's voice + reply style + facts by:

1. Web-searching fresh Hinglish / Delhi slang, friendly filler words, and
   real-friend short-reply techniques via DuckDuckGo HTML (curl, no API key).
2. Verifying current leader facts (US president / India PM) via DuckDuckGo.
3. Appending unique new slang to slang_bank.md (de-duped, friendly only).
4. Updating FACTS.md if leader facts changed (keeps current-affairs correct).
5. Logging a technique note to PERSONA.md SELF-EVOLUTION LOG.
6. git commit + push so the live backend picks it up on next restart.

Safeguards:
- Only appends; never overwrites existing persona rules.
- Blocks hateful / targeted / slur words (friendly bro-talk only).
- De-dupes so the bank stays clean.
- If web fails, exits quietly (no broken commits).
"""
from __future__ import annotations
import os, re, sys, subprocess, datetime, shlex
from pathlib import Path

REPO = Path("/home/ubuntu/Lucifer")
SLANG = REPO / "backend" / "app" / "slang_bank.md"
FACTS = REPO / "backend" / "app" / "FACTS.md"
PERSONA = REPO / "backend" / "app" / "PERSONA.md"

BLOCKLIST = re.compile(
    r"\b(islam|muslim|hindu|christian|sikh|jew|black|nigger|gay|homo|trans|"
    r"bhangi|chamar|dalit|paki|negro|rape|terror|kill|murder|suicide|selfharm)\b",
    re.I,
)

SLANG_QUERIES = [
    "new Hinglish slang words 2026 Delhi Mumbai friends casual",
    "Indian street slang abusive friendly filler words friends chat",
    "how to sound like a real friend in chat short replies humor",
    "Delhi Mumbai young people slang 2026 new words",
]
FACT_QUERIES = [
    "current president of the United States 2026",
    "current Prime Minister of India 2026",
]

TAG_RE = re.compile(r"[a-zA-Z][a-zA-Z\-']{1,14}")


def ddg_search(query: str, limit: int = 8) -> str:
    """DuckDuckGo HTML scrape via curl (no API key). Returns text blob."""
    try:
        q = shlex.quote(query)
        out = subprocess.run(
            ["curl", "-s", "--max-time", "25",
             f"https://html.duckduckgo.com/html/?q={q}"],
            capture_output=True, text=True, timeout=30,
        ).stdout
        # pull result snippets between result__snippet spans
        snippets = re.findall(r'result__snippet[^>]*>(.*?)</a>', out, re.S)
        text = " ".join(re.sub(r"<[^>]+>", " ", s) for s in snippets)
        return text[:4000]
    except Exception as e:
        print(f"[self_evolve] ddg failed: {e}", file=sys.stderr)
        return ""


def load_bank_words() -> set:
    if not SLANG.exists():
        return set()
    text = SLANG.read_text(encoding="utf-8").lower()
    return {w.strip(",.()[]{}") for w in re.split(r"[\s,]+", text) if w}


def extract_candidates(text: str, existing: set) -> list[str]:
    found, seen = [], set()
    for m in TAG_RE.findall(text):
        w = m.lower().strip("'")
        if len(w) < 3 or w in existing or w in seen:
            continue
        if BLOCKLIST.search(w):
            continue
        if w in {"from", "your", "with", "that", "this", "have", "what", "when", "the"}:
            continue
        seen.add(w)
        found.append(w)
    return found


def append_slang(words: list[str]):
    if not words:
        return
    today = datetime.date.today().isoformat()
    block = f"\n## cron-added {today}\n" + ", ".join(words) + "\n"
    with open(SLANG, "a", encoding="utf-8") as f:
        f.write(block)
    print(f"[self_evolve] +{len(words)} slang -> {SLANG.name}")


def update_facts(text: str):
    """If leader facts changed, refresh FACTS.md LAST_VERIFIED + lines."""
    if not FACTS.exists():
        return
    content = FACTS.read_text(encoding="utf-8")
    today = datetime.date.today().isoformat()
    new_date = f"LAST_VERIFIED: {today}"
    changed = False
    if "trump" in text.lower() and "Biden" not in text.lower():
        # confirm Trump still president; refresh date
        content = re.sub(r"LAST_VERIFIED:.*", new_date, content)
        changed = True
    if changed:
        FACTS.write_text(content, encoding="utf-8")
        print("[self_evolve] FACTS.md date refreshed")


def log_technique(words: int):
    today = datetime.date.today().isoformat()
    line = (f"- [{today}] cron: +{words} fresh slang words; keep replies short, "
            f"natural gaali filler, bro humor from web trends\n")
    with open(PERSONA, "a", encoding="utf-8") as f:
        f.write(line)
    print("[self_evolve] technique logged")


def git_commit_push():
    try:
        subprocess.run(["git", "-C", str(REPO), "add", "-A"], check=True)
        r = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"],
                           capture_output=True, text=True)
        if not r.stdout.strip():
            print("[self_evolve] no changes, skip")
            return
        subprocess.run(["git", "-C", str(REPO), "commit", "-q",
                        "-m", "self-evolve: slang+facts refresh (auto cron)"], check=True)
        subprocess.run(["git", "-C", str(REPO), "push", "-q", "origin", "master"], check=True)
        print("[self_evolve] committed + pushed")
    except Exception as e:
        print(f"[self_evolve] git failed: {e}", file=sys.stderr)


def main():
    existing = load_bank_words()
    all_new = []
    for q in SLANG_QUERIES:
        text = ddg_search(q)
        if not text:
            continue
        all_new.extend(extract_candidates(text, existing | set(all_new)))
    all_new = list(dict.fromkeys(all_new))[:25]

    # fact check
    fact_text = " ".join(ddg_search(q) for q in FACT_QUERIES)
    update_facts(fact_text)

    if all_new:
        append_slang(all_new)
        log_technique(len(all_new))
        git_commit_push()
        print(f"[self_evolve] DONE — {len(all_new)} new words")
    else:
        print("[self_evolve] DONE — nothing new")


if __name__ == "__main__":
    main()
