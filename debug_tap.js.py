"""
Detailed Playwright test — logs every console message + error during tap
to see exactly where the mic flow breaks.
"""
import asyncio, time
from playwright.async_api import async_playwright

STUB = """
  // Stub browser media — fake stream + recording
  window.__tapLogs = [];
  navigator.mediaDevices.getUserMedia = async () => {
    window.__tapLogs.push('getUserMedia called');
    const ctx = new (window.AudioContext||window.webkitAudioContext)();
    const dst = ctx.createMediaStreamDestination();
    window.__tapLogs.push('getUserMedia RESOLVED with stream');
    return dst.stream;
  };
  const MR = window.MediaRecorder;
  window.MediaRecorder = class extends MR {
    start(){ 
      window.__tapLogs.push('MediaRecorder.start called');
      super.start(); 
      // emit a small blob so onstop fires
      setTimeout(()=>{ 
        window.__tapLogs.push('emitting dataavailable');
        this.dispatchEvent(new Event('dataavailable')); 
      }, 100); 
      // auto-stop after 150ms
      setTimeout(()=>this.stop(), 150); 
    }
    stop(){ window.__tapLogs.push('MediaRecorder.stop'); super.stop(); }
  };
"""

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context()
        pg = await ctx.new_page()
        await pg.add_init_script(STUB)
        console_msgs = []
        pg.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
        pg.on("pageerror", lambda e: console_msgs.append(f"PAGEERR: {e}"))
        await pg.goto("https://lucifer-eight.vercel.app/")
        await pg.wait_for_timeout(500)
        # tap the orb
        await pg.evaluate("document.getElementById('orb').dispatchEvent(new PointerEvent('pointerup',{bubbles:true}))")
        await pg.wait_for_timeout(800)
        # check states
        listening = await pg.evaluate("document.getElementById('orb').classList.contains('listening')")
        busy = await pg.evaluate("typeof window.busy !== 'undefined' ? window.busy : 'n/a'")
        logs = await pg.evaluate("window.__tapLogs || []")
        print("=== Tap logs ===")
        for l in logs: print(" ", l)
        print("\n=== Console messages ===")
        for m in console_msgs: print(" ", m)
        print(f"\nlistening class: {listening}")
        await b.close()

asyncio.run(main())
