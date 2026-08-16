"""FINAL COMPREHENSIVE TEST"""
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
        await pg.add_init_script(STUB)
        await pg.goto("https://lucifer-eight.vercel.app/")
        await pg.wait_for_timeout(1000)
        
        print("=" * 60)
        print("FINAL COMPREHENSIVE TEST — Lucifer Voice Assistant")
        print("=" * 60)
        
        # TEST 1: Page Load
        print("\n[TEST 1] Page Load")
        title = await pg.title()
        orb = await pg.evaluate("!!document.getElementById('orb')")
        micBtn = await pg.evaluate("!!document.getElementById('micBtn')")
        footer = await pg.evaluate("document.body.innerHTML.includes('EntouragedSam')")
        print(f"  Title: {title}")
        print(f"  Orb: {'YES' if orb else 'NO'}")
        print(f"  MicBtn: {'YES' if micBtn else 'NO'}")
        print(f"  Footer: {'YES' if footer else 'NO'}")
        
        # TEST 2: Backend Health
        print("\n[TEST 2] Backend Health")
        h = await pg.evaluate("fetch('/api/health').then(r=>r.json())")
        print(f"  Status: {h.get('status','?')}")
        print(f"  Model: {h.get('model','?')}")
        
        # TEST 3: Text Chat
        print("\n[TEST 3] Text Chat")
        await pg.evaluate("document.getElementById('textBtn').click()")
        await pg.wait_for_timeout(200)
        await pg.evaluate("document.getElementById('textInput').value = 'Kaise ho?'")
        await pg.evaluate("document.getElementById('sendBtn').click()")
        await pg.wait_for_timeout(3000)
        reply = await pg.evaluate("document.querySelector('.transcript .lu')?.textContent?.substring(0,50) || 'NO REPLY'")
        print(f"  Reply: {reply}")
        
        # TEST 4: Voice Tap
        print("\n[TEST 4] Voice Tap → Listen")
        await pg.evaluate("document.getElementById('orb').dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}))")
        await pg.wait_for_timeout(400)
        s1 = await pg.evaluate("document.getElementById('orb').classList.contains('listening')")
        print(f"  Listening: {s1}")
        
        # TEST 5: Full Cycle
        print("\n[TEST 5] Full Voice Cycle")
        print("  Waiting 18s...")
        await pg.wait_for_timeout(18000)
        flow = await pg.evaluate("window.__flow || []")
        s2 = await pg.evaluate("document.getElementById('orb').classList.contains('listening')")
        print(f"  Flow: {flow}")
        print(f"  Auto-resumed: {s2}")
        
        # TEST 6: Errors
        print("\n[TEST 6] Errors")
        errs = [l for l in logs if l and 'ERR' in l]
        print(f"  Errors: {len(errs)}")
        
        # VERDICT
        print("\n" + "=" * 60)
        passed = sum([title == "LUCIFER — Voice Assistant", h.get('model') == 'meituan/longcat-2.0:free', reply != 'NO REPLY', s1, s2, len(errs) == 0])
        print(f"Tests passed: {passed}/6")
        if passed == 6:
            print("\n✅ ALL TESTS PASSED — Lucifer fully operational!")
        else:
            print(f"\n⚠️  {6-passed} test(s) failed")
        print("=" * 60)
        
        await b.close()

asyncio.run(main())
