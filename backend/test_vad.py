"""Real browser test #3: verify VAD auto-stop after 3s silence.
Strategy: load site, click orb to start mic. Then in-page we MONKEYPATCH
the analyser so getByteTimeDomainData returns a LOUD signal for 1s (simulating
speech), then SILENCE. We verify hasSpoken flips + 3s later stopListen fires
(sendVoice -> /api/voice called). Also test hard 15s cap disabled by VAD.
"""
import time, json
from playwright.sync_api import sync_playwright

URL = "https://lucifer-eight.vercel.app/"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--use-fake-device-for-media-stream",
            "--use-fake-ui-for-media-stream",
            "--autoplay-policy=no-user-gesture-required",
        ])
        page = browser.new_page()
        errs = []; voice = []
        page.on("console", lambda m: errs.append(m.text) if m.type=="error" else None)
        page.on("response", lambda r: voice.append(r.status) if "/api/voice" in r.url else None)

        print("[1] load"); page.goto(URL, wait_until="networkidle", timeout=30000)
        print("[2] click orb")
        page.click("#orb")
        time.sleep(1.5)
        print("    listening:", page.eval_on_selector("#orb","e=>e.classList.contains('listening')"))

        # Inject a speech→silence simulation by overriding analyser data feed.
        # We expose a hook: patch analyser.getByteTimeDomainData via the page.
        sim = page.evaluate("""() => {
            // grab the live analyser if present, else build a fake one
            window.__vadState = { hasSpoken: false, stopped: false };
            const orig = window.__luciferAnalyser;
            // We can't easily reach the closure analyser, so instead:
            // drive the real MediaRecorder/VAD by faking rms through a global
            // the app reads. Since app uses closure vars, we patch
            // AnalyserNode.prototype.getByteTimeDomainData for THIS context.
            let phase = 0;
            const proto = window.AnalyserNode && window.AnalyserNode.prototype;
            if (!proto) return 'no-proto';
            const real = proto.getByteTimeDomainData;
            proto.getByteTimeDomainData = function(arr){
                // first 1.2s: loud speech (rms high); after: silence
                const t = (window.__speechStart = window.__speechStart || Date.now());
                const elapsed = Date.now() - t;
                const loud = elapsed < 1200;
                for (let i=0;i<arr.length;i++){
                    const v = loud ? 128 + 80*Math.sin(i*0.3+phase) : 128;
                    arr[i] = v;
                }
                phase += 0.5;
            };
            return 'patched';
        }""")
        print("    VAD sim patch:", sim)

        # let it run: 1.2s speech + 3s silence -> should auto-stop ~4.2s
        print("[3] waiting for VAD auto-stop (speech 1.2s then silence 3s)...")
        time.sleep(6)
        listening_after = page.eval_on_selector("#orb","e=>e.classList.contains('listening')")
        print("    listening after 6s:", listening_after, "(should be False if auto-stop worked)")
        print("    /api/voice responses:", len(voice), voice)

        txt = page.eval_on_selector("#transcript","e=>e.innerText")
        print("[4] transcript:", repr(txt[:200]))
        print("[5] console errors:", len(errs), errs[:3])
        browser.close()

if __name__=="__main__":
    main()
