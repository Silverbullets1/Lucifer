"""
Live STT test AFTER fix (language='hi'):
- Generate real Hindi speech via /tts
- Feed to /voice 
- Check STT output is proper Hindi/Roman, NOT Arabic/Urdu garbage
"""
import requests, io, time

BASE = "https://lucifer-eight.vercel.app/api"

print("=== Health ===")
h = requests.get(f"{BASE}/health", timeout=15)
print(f"  {h.status_code} -> {h.json() if h.ok else h.text[:60]}")

print("\n=== Generate Hindi speech ===")
r1 = requests.post(f"{BASE}/tts", json={"text": "नमस्ते ल्यूसिफर मैं सैम हूँ आप कैसे हैं"}, timeout=30)
print(f"  /tts: {r1.status_code} | {len(r1.content)} bytes")
speech = r1.content

print("\n=== Feed to /voice (test STT) ===")
rv = requests.post(f"{BASE}/voice",
    files={"audio": ("mic.mp3", io.BytesIO(speech), "audio/mpeg")},
    timeout=60)
print(f"  /voice: {rv.status_code}")
if rv.ok:
    j = rv.json()
    stt = j.get("text", "")
    print(f"  STT: '{stt}'")
    # Check if Arabic chars present (the bug indicator)
    arabic_ranges = any(ord(c) > 0x0600 and ord(c) < 0x06FF for c in stt)
    if arabic_ranges:
        print("  ❌ STILL BROKEN — Arabic/Urdu script in output")
    elif stt:
        print("  ✅ FIXED — proper text (no Arabic garbage)")
    else:
        print("  ⚠️ Empty STT")
    print(f"  LLM reply: '{j.get('reply','')[:70]}'")
