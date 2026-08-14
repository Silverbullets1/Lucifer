"""Speech-to-Text for Lucifer.

Backend priority (per SAM):
  1. OpenAI Whisper through the Nous Tool Gateway  -> FREE, key-less,
     better Hinglish accuracy, offloads the VPS CPU. (default)
  2. Local faster-whisper  -> offline fallback if the gateway/network fails.

The Nous gateway URL + subscriber token are read live from
~/.hermes/auth.json (same store Hermes Agent uses) so no API key is
hard-coded. The token auto-refreshes (Hermes handles expiry), and we
also refresh it here if it is within 120s of expiring.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import Settings

log = logging.getLogger("lucifer.stt")

_models: dict = {}

# OpenAI audio vendor on the Nous gateway.
_OPENAI_AUDIO_MODEL = "whisper-1"
_REFRESH_SKEW = 120  # seconds


# --------------------------------------------------------------------------- #
# Local faster-whisper (fallback)
# --------------------------------------------------------------------------- #
def _to_wav(audio_bytes: bytes, suffix: str = ".webm") -> str:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        path = f.name
    wav_path = path.rsplit(".", 1)[0] + ".wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", path, "-ar", "16000", "-ac", "1", wav_path],
        capture_output=True, timeout=30,
    )
    os.unlink(path)
    return wav_path


def _get_model(name: str):
    if name not in _models:
        from faster_whisper import WhisperModel
        _models[name] = WhisperModel(name, device="cpu", compute_type="int8")
    return _models[name]


def _run_local(model_name: str, wav_path: str) -> str:
    model = _get_model(model_name)
    segments, _ = model.transcribe(wav_path, beam_size=5)
    return "".join(seg.text for seg in segments).strip()


# --------------------------------------------------------------------------- #
# Nous Tool Gateway (OpenAI Whisper) — primary, FREE
# --------------------------------------------------------------------------- #
def _auth_state(settings: Settings) -> Optional[dict]:
    p = Path(settings.hermes_home) / "auth.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    nous = (data.get("providers") or {}).get("nous")
    return nous if isinstance(nous, dict) else None


def _token_expiring(nous: dict) -> bool:
    exp = nous.get("expires_at")
    if not isinstance(exp, str) or not exp.strip():
        return True
    if exp.endswith("Z"):
        exp = exp[:-1] + "+00:00"
    try:
        expires = datetime.fromisoformat(exp)
    except ValueError:
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    remaining = (expires - datetime.now(timezone.utc)).total_seconds()
    return remaining <= _REFRESH_SKEW


def _refresh_token(nous: dict) -> Optional[str]:
    """Refresh the Nous access token via the Portal token endpoint."""
    portal = (nous.get("portal_base_url") or "https://portal.nousresearch.com").rstrip("/")
    url = portal + "/api/oauth/token"
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": nous.get("refresh_token", ""),
        "client_id": nous.get("client_id", "hermes-cli"),
        "scope": nous.get("scope", "inference:invoke"),
    }).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
        new_tok = resp.get("access_token")
        if new_tok:
            # Persist refreshed token + expiry back to auth.json for reuse.
            try:
                p = Path(nous.get("_auth_path")) if nous.get("_auth_path") else Path(
                    os.path.expanduser("~/.hermes/auth.json")
                )
                raw = json.loads(p.read_text(encoding="utf-8-sig"))
                np = raw.get("providers", {}).get("nous", {})
                np["access_token"] = new_tok
                if resp.get("expires_in"):
                    exp = datetime.now(timezone.utc).timestamp() + int(resp["expires_in"])
                    np["expires_at"] = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
                p.write_text(json.dumps(raw, indent=2), encoding="utf-8")
            except Exception as e:
                log.warning("nous token persist failed: %s", e)
            return new_tok
    except Exception as e:
        log.warning("nous token refresh failed: %s", e)
    return None


def _nous_whisper_transcribe(audio_bytes: bytes, settings: Settings) -> str:
    nous = _auth_state(settings)
    if not nous:
        raise RuntimeError("Nous auth.json not found")
    token = nous.get("access_token")
    if (not token) or _token_expiring(nous):
        token = _refresh_token(nous) or token
    if not token:
        raise RuntimeError("No usable Nous token")

    # Gateway origin: openai-audio-gateway.<domain>
    origin = f"{settings.nous_gateway_scheme}://openai-audio-gateway.{settings.nous_gateway_domain}"
    url = f"{origin}/v1/audio/transcriptions"

    # Whisper needs a real file; write temp.
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(audio_bytes)
        in_path = f.name
    wav_path = _to_wav(audio_bytes)

    # Build multipart form manually (no extra deps).
    boundary = "----luciferwhisperboundary"
    try:
        body = bytearray()
        # file part
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
        body += b"Content-Type: audio/wav\r\n\r\n"
        with open(wav_path, "rb") as wf:
            body += wf.read()
        body += b"\r\n"
        # model part
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="model"\r\n\r\n'
        body += _OPENAI_AUDIO_MODEL.encode() + b"\r\n"
        # language hint (hi helps Hinglish transcribe accuracy)
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="language"\r\n\r\n'
        body += b"hi\r\n"
        body += f"--{boundary}--\r\n".encode()

        req = urllib.request.Request(url, data=bytes(body), method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
        text = (resp.get("text") or "").strip()
        if not text:
            raise RuntimeError("empty transcription")
        return text
    finally:
        for p in (in_path, wav_path):
            if os.path.exists(p):
                os.unlink(p)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def transcribe(audio_bytes: bytes, settings: Settings) -> str:
    if settings.stt_backend == "nous_whisper":
        try:
            return _nous_whisper_transcribe(audio_bytes, settings)
        except Exception as e:
            log.warning("STT primary (nous_whisper) failed: %s — falling back to local", e)

    # Fallback: local faster-whisper (small -> base)
    wav_path = _to_wav(audio_bytes)
    try:
        txt = _run_local(settings.stt_model, wav_path)
        if txt:
            return txt
    except Exception as e:
        log.warning("STT local (%s) failed: %s", settings.stt_model, e)
    try:
        return _run_local("base", wav_path)
    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)
