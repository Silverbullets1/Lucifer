from playwright.sync_api import sync_playwright
import time
URL = "https://lucifer-eight.vercel.app/"
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=[
        "--use-fake-device-for-media-stream","--use-fake-ui-for-media-stream",
        "--autoplay-policy=no-user-gesture-required"])
    pg = b.new_page()
    errs=[]; pg.on("console", lambda m: errs.append(m.text) if m.type=="error" else None)
    pg.goto(URL, wait_until="networkidle", timeout=30000)
    print("title:", pg.title())
    # orb click -> listening True (mic init + SR VAD start)
    pg.click("#orb"); time.sleep(2)
    print("listening after orb click:", pg.eval_on_selector("#orb","e=>e.classList.contains('listening')"))
    print("micBtn label:", pg.eval_on_selector("#micBtn","e=>e.textContent"))
    # verify 15s hard cap by waiting (no manual stop)
    print("waiting 16s for hard-cap auto-stop...")
    time.sleep(16)
    print("listening after 16s (hard cap should stop):", pg.eval_on_selector("#orb","e=>e.classList.contains('listening')"))
    print("console errors:", errs)
    b.close()
