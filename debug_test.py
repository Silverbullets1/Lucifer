"""DEBUG TEST — Find exact issue"""
import asyncio, time
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
      setTimeout(()=>this.stop(), 2500);
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
        
        # Check if API_BASE is defined
        has_api_base = await pg.evaluate("typeof API_BASE !== 'undefined'")
        print(f"API_BASE defined: {has_api_base}")
        
        # Try text chat
        print("\n=== Text Chat ===")
        await pg.evaluate("document.getElementById('textBtn').click()")
        await pg.wait_for_timeout(300)
        await pg.evaluate("document.getElementById('textInput').value = 'Hello'")
        await pg.evaluate("document.getElementById('sendBtn').click()")
        await pg.wait_for_timeout(3000)
        transcript = await pg.evaluate("document.querySelector('.transcript')?.textContent?.substring(0,80) || 'EMPTY'")
        print(f"Transcript: {transcript}")
        
        # Try voice tap
        print("\n=== Voice Tap ===")
        await pg.evaluate("document.getElementById('orb').dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}))")
        await pg.wait_for_timeout(500)
        listening = await pg.evaluate("document.getElementById('orb').classList.contains('listening')")
        print(f"Listening: {listening}")
        
        # Wait for cycle
        await pg.wait_for_timeout(18000)
        
        flow = await pg.evaluate("window.__flow || []")
        print(f"Flow: {flow}")
        
        print(f"\nLogs: {logs[:5]}")
        
        await b.close()

asyncio.run(main())
