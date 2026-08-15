from playwright.sync_api import sync_playwright
import time
URL = "https://lucifer-eight.vercel.app/"

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=[
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
        "--autoplay-policy=no-user-gesture-required"])
    pg = b.new_page()
    errs=[]; pg.on("console", lambda m: errs.append(m.text) if m.type=="error" else None)
    pg.goto(URL, wait_until="networkidle", timeout=30000)

    # Directly test analyseChunk by injecting a loud wav blob + silence wav blob,
    # and checking whether stopListen fires after 3s of silence.
    res = pg.evaluate("""async () => {
        // build a loud 300ms wav
        function wav(loud){
            const sr=16000, n=sr*0.3;
            const buf=new ArrayBuffer(44+n*2), v=new DataView(buf);
            const wr=(o,s)=>{for(let i=0;i<s.length;i++)v.setUint8(o+i,s.charCodeAt(i));};
            wr(0,'RIFF');v.setUint32(4,36+n*2,true);wr(8,'WAVE');wr(12,'fmt ');
            v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);
            v.setUint32(24,sr,true);v.setUint32(28,sr*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);
            wr(36,'data');v.setUint32(40,n*2,true);
            for(let i=0;i<n;i++){const s=loud?9000*Math.sin(i*0.1):0;v.setInt16(44+i*2,s,true);}
            return new Blob([buf],{type:'audio/wav'});
        }
        window.__stopped = false;
        const origStop = stopListen;
        // patch stopListen to record call
        // can't reassign function decl easily; instead check via listening class later
        // Simulate: speech chunk then silence chunks
        vadActive = true; hasSpoken = false;
        await analyseChunk(wav(true));   // speech
        const spoke = hasSpoken;
        await analyseChunk(wav(false));  // silence #1
        const t1 = !!silenceTimer;
        // wait 3.2s -> silence timer should fire stopListen
        await new Promise(r=>setTimeout(r,3300));
        return { spoke, silenceTimerStarted: t1, listeningNow: document.getElementById('orb').classList.contains('listening') };
    }""")
    print("RESULT:", res)
    print("console errors:", len(errs), errs[:3])
    b.close()
