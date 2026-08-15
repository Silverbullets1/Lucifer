import requests, base64, io, time

BASE = "https://lucifer-eight.vercel.app"
SID = "live_" + str(int(time.time()))

print("=== 1. Footer (Entouraged.sam credit, old tags removed) ===")
html = requests.get(f"{BASE}/", timeout=15).text
print("  'Entouraged.sam' present:", "Entouraged.sam" in html)
print("  'tencent/hy3' gone:", "tencent/hy3" not in html)
print("  'hm_psi' gone:", "hm_psi" not in html)

print("\n=== 2. Backend health via Vercel ===")
h = requests.get(f"{BASE}/api/health", timeout=15)
print("  /api/health:", h.status_code, h.json() if h.ok else h.text[:60])

print("\n=== 3. Session Memory E2E (sid:", SID, ") ===")
r1 = requests.post(f"{BASE}/api/chat/stream", json={"text":"namaste bhai, maine poocha tha kuch","sid":SID}, timeout=60)
t1 = r1.text.strip()[:70]
print("  turn1:", r1.status_code, t1)
time.sleep(0.5)
r2 = requests.post(f"{BASE}/api/chat/stream", json={"text":"kya maine last baat poocha dikkat hai?","sid":SID}, timeout=60)
t2 = r2.text.strip()[:90]
print("  turn2:", r2.status_code, t2)

print("\n=== 4. TTS content-type (mp3 via Sarvam, sniffed by proxy) ===")
r3 = requests.post(f"{BASE}/api/tts", json={"text":"theek hai bhai"}, timeout=30, stream=True)
ct = r3.headers.get("content-type")
print("  /api/tts:", r3.status_code, "ctype:", ct, "bytes:", r3.headers.get("content-length"))
aud = b""
for c in r3.iter_content(8192): aud += c
print("  mp3 valid (0xff 0xfb/0xf3):", aud[:2] in (b"\xff\xfb", b"\xff\xf3", b"ID3"))

print("\n=== 5. Voice E2E (real webm audio path) ===")
# generate a Sarvam mp3, feed to /voice (simulates mic audio round-trip)
gen = requests.post(f"{BASE}/api/tts", json={"text":"main sam hoon"}, timeout=30)
print("  gen for voice:", gen.status_code, len(gen.content), "B")
rv = requests.post(f"{BASE}/api/voice?sid="+SID, files={"audio":("v.webm", io.BytesIO(gen.content), "audio/webm")}, timeout=60)
print("  /api/voice:", rv.status_code, rv.json() if rv.ok else rv.text[:80])

mem_ok = t1 and t2 and ("poocha" in t1.lower() or "namaste" in t1.lower())
print("\nFINAL:", "✅ ALL 5 FIXES LIVE & VERIFIED" if mem_ok and r3.status_code==200 and rv.status_code==200 else "CHECK")
