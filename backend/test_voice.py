"""Real browser test: load live site, click orb, verify mic + /api/voice chain.
Uses Playwright Chromium with --use-fake-device-for-media-stream so the mic
produces a synthetic tone (proves getUserMedia + MediaRecorder + fetch path).
"""
import sys, json, time
from playwright.sync_api import sync_playwright

URL = "https://lucifer-eight.vercel.app/"

console_errors = []
network_voice = []

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
                "--autoplay-policy=no-user-gesture-required",
            ],
        )
        page = browser.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("request", lambda r: network_voice.append(r.url) if "/api/voice" in r.url else None)
        page.on("requestfinished", lambda r: network_voice.append("DONE:"+r.url) if "/api/voice" in r.url else None)

        print("[1] loading", URL)
        page.goto(URL, wait_until="networkidle", timeout=30000)
        print("[2] page loaded. title:", page.title())

        # check key elements exist
        for sel in ["#orb", "#micBtn", "#app", "#transcript"]:
            ok = page.query_selector(sel) is not None
            print(f"    element {sel}: {'OK' if ok else 'MISSING'}")

        # check orb has a click listener (dispatch click, see if listening class appears)
        print("[3] clicking orb (toggle mic)...")
        page.click("#orb")
        time.sleep(2)  # allow getUserMedia + MediaRecorder.start + VAD
        listening = page.eval_on_selector("#orb", "el => el.classList.contains('listening')")
        print(f"    orb listening class after click: {listening}")
        mic_label = page.eval_on_selector("#micBtn", "el => el.textContent")
        print(f"    micBtn label: {mic_label!r}")

        # let it record ~4s (fake stream is silent -> VAD 3s silence after speech,
        # but fake stream has no speech so hasSpoken stays false; force stop)
        time.sleep(4)
        print("[4] forcing stop via mic button click")
        page.click("#micBtn")
        time.sleep(3)  # allow sendVoice -> fetch /api/voice -> response

        print("[5] network /api/voice calls:", len(network_voice))
        for n in network_voice[:10]:
            print("    ", n)

        print("[6] console errors:", len(console_errors))
        for e in console_errors[:10]:
            print("    ", e)

        # transcript content
        txt = page.eval_on_selector("#transcript", "el => el.innerText")
        print("[7] transcript:", repr(txt[:300]))

        browser.close()

if __name__ == "__main__":
    main()
