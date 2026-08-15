from playwright.sync_api import sync_playwright
import time
URL = "https://lucifer-eight.vercel.app/"

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=[
        "--use-fake-device-for-media-stream","--use-fake-ui-for-media-stream",
        "--autoplay-policy=no-user-gesture-required"])
    pg = b.new_page()
    pg.goto(URL, wait_until="networkidle", timeout=30000)
    res = pg.evaluate("""async () => {
        function wav(loud){
            const sr=16000, n=Math.floor(sr*0.3);
            const buf=new ArrayBuffer(44+n*2), v=new DataView(buf);
            const wr=(o,s)=>{for(let i=0;i<s.length;i++)v.setUint8(o+i,s.charCodeAt(i));};
            wr(0,'RIFF');v.setUint32(4,36+n*2,true);wr(8,'WAVE');wr(12,'fmt ');
            v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);
            v.setUint32(24,sr,true);v.setUint32(28,sr*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);
            wr(36,'data');v.setUint32(40,n*2,true);
            for(let i=0;i<n;i++){const s=loud?9000*Math.sin(i*0.1):0;v.setInt16(44+i*2,s,true);}
            return new Blob([buf],{type:'audio/wav'});
        }
        const blob = wav(true);
        const arr = await blob.arrayBuffer();
        let decoded=null, err=null, rms=null;
        try {
            decoded = await audioCtx.decodeAudioData(arr.slice(0));
            const d = decoded.getChannelData(0);
            let s=0; for(let i=0;i<d.length;i++) s+=d[i]*d[i];
            rms = Math.sqrt(s/d.length);
        } catch(e){ err = String(e); }
        return { hasCtx: !!audioCtx, decoded: !!decoded, err, rms,
                 audioCtxState: audioCtx ? audioCtx.state : 'none' };
    }""")
    print("DEBUG:", res)
    b.close()
