"""DEBUG — Voice Tap"""
import asyncio
from playwright.async_api import async_playwright

STUB = """
  window.__flow = [];
  navigator.mediaDevices.getUserMedia = async () => {
    window.__flow.push('getUserMedia');
    const ctx = new (window.AudioContext||window.webkitAudioContext)();
    window.__flow.push('stream-OK');
    return ctx.createMediaStreamDestination().stream;
  };
  const MR = window.MediaRecorder;
  window.MediaRecorder = class extends MR {
    start(){ window.__flow.push('recorder-start'); super.start();
      setTimeout(()=>{ window.__flow.push('dataavailable'); this.dispatchEvent(new Event('dataavailable')); }, 50);
    }
    stop(){ window.__flow.push('recorder-stop'); super.stop(); }
  };
"""

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context()
        pg = await ctx.new_page()
        logs = []
        pg.on("pageerror", lambda e: logs.append(f"ERR: {e}"))
        pg.on("console", lambda m: logs.append(f"[{m.type}] {m.text}" if "error" in m.text.lower() else None))
        await pg.add_init_script(STUB)
        await pg.goto("https://lucifer-eight.vercel.app/")
        await pg.wait_for_timeout(1000)
        
        # Check hasMediaSupport
        has_media = await pg.evaluate("hasMediaSupport()")
        print(f"hasMediaSupport: {has_media}")
        
        # Check MediaRecorder available
        has_mr = await pg.evaluate("typeof MediaRecorder !== 'undefined'")
        print(f"MediaRecorder: {has_mr}")
        
        # Call startListen directly
        result = await pg.evaluate("""() => {
          try {
            startListen();
            return { ok: true, listening: listening, conversationOn: conversationOn };
          } catch(e) {
            return { ok: false, err: e.message };
          }
        }""")
        print(f"startListen result: {result}")
        
        # Now tap
        await pg.evaluate("document.getElementById('orb').dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}))")
        await pg.wait_for_timeout(500)
        listening = await pg.evaluate("document.getElementById('orb').classList.contains('listening')")
        print(f"Listening after tap: {listening}")
        
        # Wait and check
        await pg.wait_for_timeout(5000)
        flow = await pg.evaluate("window.__flow || []")
        print(f"Flow: {flow}")
        
        print(f"Logs: {logs[:5]}")
        
        await b.close()

asyncio.run(main())
