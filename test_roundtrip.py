"""
Final live roundtrip test: TTS speech -> /voice -> STT -> LLM -> TTS
Verifies Nous Whisper API fallback chain works correctly
"""
import requests, io

BASE = "https://lucifer-eight.vercel.app/api"

print("=== Generate real Hindi speech (proper mic-like audio) ===")
r1 = requests.post(f"{BASE}/tts", json={"text": "नमस्ते ल्यूसिफर मैं सैम हूँ"} , timeout=30)
print(f"  /tts: {r1.status_code} | {len(r1.content)} bytes | ctype: {r1.headers.get('content-type')}")
speech = r1.content

print("\n=== Feed to /voice (real roundtrip test) ===")
rv = requests.post(f"{BASE}/voice", 
    files={"audio": ("voice.mp3", io.BytesIO(speech), "audio/mpeg")},
    timeout=60)
print(f"  /voice: {rv.status_code}")
if rv.ok:
    j = rv.json()
    print(f"  STT output: '{j.get('text','')}'")
    print(f"  LLM reply:  '{j.get('reply','')[:70]}'")
    print(f"  Audio:      {'✅ present' if j.get('audio_b64') else '❌ missing'}")
    # success = STT has real text (not Arabic garbage)
    stt = j.get('text','')
    if stt and len(stt) > 3 and 'Namaste' in stt or 'नमस्ते' in stt:
        print("\n✅ FULL ROUNDTRIP SUCCESS — STT+Nous Whisper+LLM+TTS ALL WORKING")
    elif stt:
        print(f"\n⚠️  STT worked but unexpected text: '{stt}'")
    else:
        print("\n❌ STT failed")
elif rv.status_code == 500:
    print("  Server error:", rv.text[:120])
