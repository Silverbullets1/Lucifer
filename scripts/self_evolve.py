#!/usr/bin/env python3
"""
LUCIFER SELF-EVOLUTION CRON
===========================
Runs on a schedule. Self-improves Lucifer's voice + reply style by:

1. Web-searching fresh Hinglish / Delhi slang, abusive-but-friendly filler
   words, and real-friend reply/entertainment techniques.
2. Extracting unique candidates not already in slang_bank.md / PERSONA.md.
3. Appending new words to slang_bank.md (curated, de-duplicated).
4. Appending a dated technique note to PERSONA.md SELF-EVOLUTION LOG.
5. git commit + push so the live backend picks it up on next restart.

Safeguards:
- Only appends; never overwrites existing content.
- Filters out hateful / targeted / slur words (keeps it friendly bro-talk).
- De-duplicates against existing bank so the file stays clean.
- If web search fails, exits quietly (no broken commits).
"""
from __future__ import annotations
import os, re, sys, json, subprocess, datetime
from pathlib import Path

# Allow importing hermes web_search helper from the bridge.
_HERMES = Path("/home/ubuntu/hermes-agent")
if str(_HERMES) not in sys.path:
    sys.path.insert(0, str(_HERMES))

REPO = Path("/home/ubuntu/Lucifer")
SLANG = REPO / "backend" / "app" / "slang_bank.md"
PERSONA = REPO / "backend" / "app" / "PERSONA.md"

# Hateful / targeted / slur roots we NEVER add (keep it friendly bro-talk).
BLOCKLIST = re.compile(
    r"\b(islam|muslim|hindu|christian|sikh|jew|black|nigger|gay|homo|trans|"
    r"bhangi|chamar|dalit|paki|negro|rape|terror|kill|murder|suicide|self harm)\b",
    re.I,
)

QUERIES = [
    "new Hinglish slang words 2026 Delhi Mumbai friends casual",
    "Indian street slang abusive friendly filler words friends chat",
    "how to sound like a real friend in chat short replies humor",
    "Delhi Mumbai young people slang 2026 new words",
]

# Tags we extract from search snippets.
TAG_RE = re.compile(r"[a-zA-Z][a-zA-Z\-\']{1,14}")


def web_search(query: str, limit: int = 5) -> str:
    try:
        from hermes_tools import web_search as ws
        r = ws(query=query, limit=limit)
        out = []
        for item in r.get("data", {}).get("web", []):
            out.append(item.get("title", ""))
            out.append(item.get("description", ""))
        return "\n".join(out)
    except Exception as e:
        print(f"[self_evolve] web_search failed: {e}", file=sys.stderr)
        return ""


def load_bank_words() -> set:
    if not SLANG.exists():
        return set()
    text = SLANG.read_text(encoding="utf-8").lower()
    # grab all comma/space separated tokens
    return {w.strip(",./()[]{}") for w in re.split(r"[\s,]+", text) if w}


def extract_candidates(text: str, existing: set) -> list[str]:
    found = []
    seen = set()
    for m in TAG_RE.findall(text):
        w = m.lower().strip("'")
        if len(w) < 3:
            continue
        if w in existing or w in seen:
            continue
        if BLOCKLIST.search(w):
            continue
        # skip pure english common words already likely present
        if w in {"from", "your", "with", "that", "this", "have", "what", "when"}:
            continue
        seen.add(w)
        found.append(w)
    return found


def append_slang(words: list[str]):
    if not words:
        return
    # group under a date header if not present, append comma list
    today = datetime.date.today().isoformat()
    block = "\n## cron-added " + today + "\n" + ", ".join(words) + "\n"
    with open(SLANG, "a", encoding="utf-8") as f:
        f.write(block)
    print(f"[self_evolve] +{len(words)} slang words -> {SLANG.name}")


def append_technique(note: str):
    today = datetime.date.today().isoformat()
    # insert before the final GOAL/LOG closing — we append at end of LOG section.
    line = f"- [{today}] cron: {note}\n"
    with open(PERSONA, "a", encoding="utf-8") as f:
        f.write(line)
    print(f"[self_evolve] technique logged: {note[:60]}")


def git_commit_push():
    try:
        subprocess.run(["git", "-C", str(REPO), "add", "-A"], check=True)
        # only commit if there are changes
        r = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"],
                           capture_output=True, text=True)
        if not r.stdout.strip():
            print("[self_evolve] no changes, skip commit")
            return
        subprocess.run(["git", "-C", str(REPO), "commit", "-q",
                        "-m", "self-evolve: new slang + techniques (auto cron)"],
                       check=True)
        subprocess.run(["git", "-C", str(REPO), "push", "-q", "origin", "master"],
                       check=True)
        print("[self_evolve] committed + pushed")
    except Exception as e:
        print(f"[self_evolve] git step failed: {e}", file=sys.stderr)


def main():
    existing = load_bank_words()
    all_new = []
    for q in QUERIES:
        text = web_search(q)
        if not text:
            continue
        cands = extract_candidates(text, existing | set(all_new))
        all_new.extend(cands)
    # de-dup + cap to keep it sane (max 25 new per run)
    all_new = list(dict.fromkeys(all_new))[:25]
    if all_new:
        append_slang(all_new)
        append_technique(
            f"added {len(all_new)} fresh slang words; keep replies short, "
            f"natural gaali filler, bro-style humor from web trends"
        )
        git_commit_push()
        print(f"[self_evolve] DONE — {len(all_new)} new words")
    else:
        print("[self_evolve] DONE — nothing new this run")


if __name__ == "__main__":
    main()
