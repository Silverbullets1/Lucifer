"""DEEP DEBUG — Find exact failure point"""
import asyncio
from playwright.async_api import async_playwright

STUB = """
  window.__flow = [];
  window.__debug = [];
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
        pg.on("console", lambda m: logs.append(f"[{m.type}] {m.text}" if "error" in m.text.lower() or "err" in m.text.lower() else None))
        await pg.add_init_script(STUB)
        await pg.goto("https://lucifer-eight.vercel.app/")
        await pg.wait_for_timeout(1000)
        
        # Debug 1: Is startListen defined?
        has_start_listen = await pg.evaluate("typeof startListen === 'function'")
        print(f"startListen defined: {has_start_listen}")
        
        # Debug 2: Call startListen directly
        print("\n=== Direct startListen() call ===")
        result = await pg.evaluate("""() => {
          try {
            startListen();
            return 'called';
          } catch(e) {
            return 'error: ' + e.message;
          }
        }""")
        print(f"startListen() result: {result}")
        
        # Debug 3: Check listening state
        listening = await pg.evaluate("document.getElementById('orb').classList.contains('listening')")
        print(f"Listening after startListen: {listening}")
        
        # Debug 4: Text chat - full debug
        print("\n=== Text Chat Debug ===")
        await pg.evaluate("document.getElementById('textBtn').click()")
        await pg.wait_for_timeout(200)
        await pg.evaluate("document.getElementById('textInput').value = 'Hello'")
        await pg.evaluate("document.getElementById('sendBtn').click()")
        await pg.wait_for_timeout(3000)
        
        # Check fetch result
        fetch_debug = await pg.evaluate("""() => {
          return fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text: 'Hello'})
          }).then(r => r.text()).then(t => t.substring(0, 100));
        }""")
        print(f"Chat API response: {fetch_debug}")
        
        # Debug 5: Check fetch for /api/chat/stream
        fetch_stream = await pg.evaluate("""() => {
          return fetch('/api/chat/stream', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text: 'Hello'})
          }).then(r => r.status);
        }""")
        print(f"Chat stream status: {fetch_stream}")
        
        print(f"\nLogs: {logs[:10]}")
        
        await b.close()

asyncio.run(main())
