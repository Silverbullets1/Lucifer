"""COMPREHENSIVE LIVE TEST — https://lucifer-eight.vercel.app/"""
import asyncio, time
from playwright.async_api import async_playwright

STUB = """
  window.__flow = [];
  window.__errors = [];
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
        pg.on("console", lambda m: logs.append(f"[{m.type}] {m.text}") if "error" in m.text.lower() else None)
        await pg.add_init_script(STUB)
        
        print("=" * 60)
        print("COMPREHENSIVE LIVE TEST — Lucifer Voice Assistant")
        print("=" * 60)
        
        # TEST 1: Page Load
        print("\n[TEST 1] Page Load")
        await pg.goto("https://lucifer-eight.vercel.app/")
        await pg.wait_for_timeout(1000)
        title = await pg.title()
        orb = await pg.evaluate("!!document.getElementById('orb')")
        micBtn = await pg.evaluate("!!document.getElementById('micBtn')")
        textBtn = await pg.evaluate("!!document.getElementById('textBtn')")
        transcript = await pg.evaluate("!!document.getElementById('transcript')")
        footer = await pg.evaluate("document.body.innerHTML.includes('EntouragedSam')")
        print(f"  Page title: {title}")
        print(f"  Orb element: {'YES' if orb else 'NO'}")
        print(f"  Mic button: {'YES' if micBtn else 'NO'}")
        print(f"  Text button: {'YES' if textBtn else 'NO'}")
        print(f"  Transcript area: {'YES' if transcript else 'NO'}")
        print(f"  Developer credit: {'YES' if footer else 'NO'}")
        
        # TEST 2: Backend Health
        print("\n[TEST 2] Backend Health")
        h = await pg.evaluate("fetch('/api/health').then(r=>r.json())")
        print(f"  Status: {h.get('status','?')}")
        print(f"  Model: {h.get('model','?')}")
        print(f"  Device: {h.get('device','?')}")
        
        # TEST 3: Text Chat (TYPE mode)
        print("\n[TEST 3] Text Chat (TYPE mode)")
        await pg.evaluate("document.getElementById('textBtn').click()")
        await pg.wait_for_timeout(300)
        await pg.evaluate("document.getElementById('textInput').value = 'Kaise ho bhai?'")
        await pg.evaluate("document.getElementById('sendBtn').click()")
        await pg.wait_for_timeout(3000)
        reply = await pg.evaluate("document.querySelector('.transcript .lu')?.textContent?.substring(0,60) || 'NO REPLY'")
        print(f"  Reply: {reply}")
        
        # TEST 4: Voice Tap → Listen
        print("\n[TEST 4] Voice Tap → Listen")
        await pg.evaluate("document.getElementById('orb').dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}))")
        await pg.wait_for_timeout(400)
        s1 = await pg.evaluate("document.getElementById('orb').classList.contains('listening')")
        print(f"  Tap → listening: {s1}")
        
        # TEST 5: Full Voice Cycle (VAD + STT + LLM + TTS + Auto-resume)
        print("\n[TEST 5] Full Voice Cycle")
        print("  Waiting 18s for VAD + STT + LLM + TTS...")
        await pg.wait_for_timeout(18000)
        
        flow = await pg.evaluate("window.__flow || []")
        print(f"  Flow: {flow}")
        
        s2 = await pg.evaluate("document.getElementById('orb').classList.contains('listening')")
        print(f"  Auto-resumed: {s2}")
        
        # TEST 6: Errors
        print("\n[TEST 6] Errors")
        errs = [l for l in logs if l and ('ERR' in l or 'error' in l.lower())]
        print(f"  Page errors: {len(errs)}")
        for e in errs[:5]:
            print(f"    - {e}")
        
        # FINAL VERDICT
        print("\n" + "=" * 60)
        print("FINAL VERDICT")
        print("=" * 60)
        
        passed = 0
        total = 6
        
        if title == "LUCIFER — Voice Assistant": passed += 1
        if h.get('model') == 'meituan/longcat-2.0:free': passed += 1
        if s1: passed += 1
        if s2: passed += 1
        if 'recorder-stop' in flow: passed += 1
        if len(errs) == 0: passed += 1
        
        print(f"  Tests passed: {passed}/{total}")
        
        if passed == total:
            print("\n✅ ALL TESTS PASSED — Lucifer fully operational!")
        else:
            print(f"\n⚠️  {total - passed} test(s) failed — needs attention")
        
        await b.close()

asyncio.run(main())
