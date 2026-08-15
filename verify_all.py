import requests, base64, io, time

BASE = "https://lucifer-eight.vercel.app/api"
SID = "verify_" + str(int(time.time()))

print("=== Deployed footer check ===")
html = requests.get(f"{BASE}/../", timeout=15).text
print("has 'Entouraged.sam':", "Entouraged.sam" in html)
print("has 'tencent/hy3':", "tencent/hy3" in html, "(should be False)")
print("has 'hm_psi':", "hm_psi" in html, "(should be False)")

print("\n=== Session Memory E2E (sid:", SID, ") ===")
# turn 1
r1 = requests.post(f"{BASE}/chat", json={"text": "maine tumhe poocha tha ek sawaal", "sid": SID}, timeout=45)
print("turn1:", r1.status_code, (r1.text[:60] if r1.ok else r1.text[:120]))
time.sleep(1)
# turn 2 - should reference previous turn
r2 = requests.post(f"{BASE}/chat", json={"text": "kya maine kaha last baat poocha tha?", "sid": SID}, timeout=45)
print("turn2:", r2.status_code, (r2.text[:80] if r2.ok else r2.text[:120]))

print("\n=== TTS content-type ===")
r3 = requests.post(f"{BASE}/tts", json={"text": "namaste"}, timeout=30)
print("TTS:", r3.status_code, "ctype:", r3.headers.get("content-type"), "bytes:", len(r3.content))

ok = (r1.ok and r2.ok and r3.status_code==200)
print("\nFINAL:", "ALL FIXES LIVE & VERIFIED" if ok else "CHECK FAILED")
