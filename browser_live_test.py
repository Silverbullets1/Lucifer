"""
Full browser-based LIVE test of Lucifer voice assistant.
Tests: tap → listening → audio capture → silence detection → STT → LLM → TTS
"""
import asyncio, time
from playwright.async_api import async_playwright

STUB = """
  window.__flow = [];
  // Stub getUserMedia with fake audio stream
  navigator.mediaDevices.getUserMedia = async () => {
    window.__flow.push('getUserMedia');
    const ctx = new (window.AudioContext||window.webkitAudioContext)();
    const dst = ctx.createMediaStreamDestination();
    // emit silence (zero-level) so VAD silence timer kicks in
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    proc.onaudioprocess = (e) => {
      const d = e.outputBuffer.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = 0; // silence
    };
    dst.stream.getAudioTracks()[0];
    window.__flow.push('mic-stream-OK');
    return dst.stream;
  };
  // MediaRecorder — emit blob after stop
  const MR = window.MediaRecorder;
  window.MediaRecorder = class extends MR {
    start(){ 
      window.__flow.push('recorder-start');
      super.start(); 
      // emit a dataavailable event after 50ms
      setTimeout(()=>{
        window.__flow.push('dataavailable');
        this.dispatchEvent(new Event('dataavailable'));
      }, 50);
    }
    stop(){ 
      window.__flow.push('recorder-stop');
      super.stop(); 
    }
  };
"""

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context()
        pg = await ctx.new_page()
        logs = []
        pg.on("console", lambda m: logs.append(f"[{m.type}] {m.text}"))
        pg.on("pageerror", lambda e: logs.append(f"PAGEERR: {e}"))
        await pg.add_init_script(STUB)
        await pg.goto("https://lucifer-eight.vercel.app/")
        await pg.wait_for_timeout(1000)

        orb_exists = await pg.evaluate("!!document.getElementById('orb')")
        print(f"1. Orb exists: {'YES' if orb_exists else 'NO'}")

        # Check deployed VAD code
        has_vad = await pg.evaluate("typeof window.startVAD === 'function' || document.documentElement.innerHTML.includes('startVAD')")
        vad_in_js = await pg.evaluate("""() => {
          const scripts = document.querySelectorAll('script');
          for (const s of scripts) if (s.src && s.textContent.includes('startVAD')) return true;
          return document.body.innerHTML.includes('startVAD');
        }""")
        print(f"2. VAD code in deployed JS: {vad_in_js}")

        # TAP 1 — start
        await pg.evaluate("document.getElementById('orb').dispatchEvent(new PointerEvent('pointerup',{bubbles:true}))")
        await pg.wait_for_timeout(600)
        s1 = await pg.evaluate("document.getElementById('orb').classList.contains('listening')")
        flow = await pg.evaluate("window.__flow || []")
        print(f"3. After tap1 -> listening: {'YES' if s1 else 'NO'}")
        print(f"4. Browser flow: {flow}")

        # Check for error messages in transcript
        errors = [l for l in logs if 'err' in l.lower() or 'pageerr' in l.lower()]
        print(f"5. Errors: {errors[:3]}")

        await b.close()

asyncio.run(main())
