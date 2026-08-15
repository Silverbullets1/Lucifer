from playwright.sync_api import sync_playwright
import time
URL = "https://lucifer-eight.vercel.app/"
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=[
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
        "--autoplay-policy=no-user-gesture-required"])
    pg = b.new_page()
    errs=[]; pg.on("console", lambda m: errs.append(m.text) if m.type=="error" else None)
    pg.goto(URL, wait_until="networkidle", timeout=30000)
    pg.click("#orb")
    time.sleep(1)
    print("listening @1s:", pg.eval_on_selector("#orb","e=>e.classList.contains('listening')"))
    # Chrome's fake stream emits a beep which SpeechRecognition WILL process and
    # then end (onend) -> should trigger stopListen. Wait up to 12s.
    for t in range(12):
        time.sleep(1)
        l = pg.eval_on_selector("#orb","e=>e.classList.contains('listening')")
        if not l:
            print(f"auto-stopped at ~{t+1}s"); break
    else:
        print("still listening after 12s (SR endpointing may need real speech)")
    print("console errors:", len(errs), errs[:3])
    b.close()
