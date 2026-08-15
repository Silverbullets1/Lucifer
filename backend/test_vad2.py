from playwright.sync_api import sync_playwright
import time
URL = "https://lucifer-eight.vercel.app/"
# Build a wav: 1.5s speech tone then 4s silence => should auto-stop ~5.5s
sr = 16000
import struct, wave
w = wave.open("/tmp/vad_test.wav", "wb")
w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
for i in range(sr):
    # 1.5s loud tone
    v = int(8000 * (1 if i < sr*1.5 else 0) * (0.5+0.5*__import__('math').sin(i*0.05)))
    w.writeframes(struct.pack("<h", max(-32767,min(32767,v))))
w.close()
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=[
        "--use-file-for-fake-audio-capture=/tmp/vad_test.wav",
        "--use-fake-ui-for-media-stream",
        "--autoplay-policy=no-user-gesture-required"])
    pg = b.new_page()
    pg.goto(URL, wait_until="networkidle", timeout=30000)
    pg.click("#orb")
    time.sleep(1)
    print("listening @1s:", pg.eval_on_selector("#orb","e=>e.classList.contains('listening')"))
    time.sleep(7)
    print("listening @8s (expect False = VAD auto-stop worked):",
          pg.eval_on_selector("#orb","e=>e.classList.contains('listening')"))
    b.close()
