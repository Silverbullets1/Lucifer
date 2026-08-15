from playwright.sync_api import sync_playwright
import time
URL = "https://lucifer-eight.vercel.app/"
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=[
        "--use-file-for-fake-audio-capture=/tmp/fake_mic.wav",
        "--use-fake-ui-for-media-stream",
        "--autoplay-policy=no-user-gesture-required"])
    pg = b.new_page()
    pg.goto(URL, wait_until="networkidle", timeout=30000)
    pg.click("#orb")
    time.sleep(2)
    print("listening after start:", pg.eval_on_selector("#orb", "e=>e.classList.contains('listening')"))
    time.sleep(10)
    print("listening after 10s (real file audio -> speech -> 3s silence -> stop expected False):",
          pg.eval_on_selector("#orb", "e=>e.classList.contains('listening')"))
    b.close()
