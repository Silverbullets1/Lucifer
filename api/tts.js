// LUCIFER TTS proxy — runs on Vercel serverless (NOT the browser).
// Uses Microsoft Edge TTS (en-IN-PrabhatNeural) via raw WebSocket — native
// Hindi, keyless, free. No npm dependencies (Node 18.19 has global WebSocket).
// The frontend POSTs {text, speaker?} and we return mp3 audio.

const VOICE_URL =
  "wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1?TrustedClientToken=6A5AA1D4EAFF4E9FB37E23A1B7832003";

function buildSsml(text, voice) {
  return (
    `<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="en-US">` +
    `<voice name="${voice}">` +
    `<prosody pitch="+0Hz" rate="1" volume="100">` +
    `${text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}` +
    `</prosody></voice></speak>`
  );
}

function synthesize(text, voice) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(VOICE_URL, { headers: { "User-Agent": "Mozilla/5.0" } });
    const chunks = [];
    let audioStarted = false;
    const timer = setTimeout(() => {
      try { ws.close(); } catch (_) {}
      reject(new Error("tts_timeout"));
    }, 30000);

    ws.addEventListener("open", () => {
      // 1) config
      ws.send(
        `X-Timestamp: ${new Date().toISOString()}\r\n` +
          "Content-Type: application/json; charset=utf-8\r\n" +
          "Path: speech.config\r\n\r\n" +
          JSON.stringify({
            context: {
              synthesis: {
                audio: { metadataoptions: { sentenceBoundaryEnabled: false, wordBoundaryEnabled: false }, outputFormat: "audio-24khz-48kbitrate-mono-mp3" },
              },
            },
          })
      );
      // 2) SSML
      const ssml = buildSsml(text, voice);
      ws.send(
        `X-Timestamp: ${new Date().toISOString()}\r\n` +
          "Content-Type: application/ssml+xml\r\n" +
          `Path: ssml\r\n` +
          `X-RequestId: ${Math.random().toString(36).slice(2)}\r\n` +
          `X-RequestId: ${Math.random().toString(36).slice(2)}\r\n\r\n` +
          ssml
      );
    });

    ws.addEventListener("message", (ev) => {
      const data = ev.data;
      const str = data.toString();
      if (str.includes("Path:audio")) {
        audioStarted = true;
        // audio frame: header lines then binary
        const idx = str.indexOf("\r\n\r\n");
        if (idx !== -1) {
          const tail = str.slice(idx + 4);
          if (tail.length) chunks.push(Buffer.from(tail, "binary"));
        }
      } else if (data instanceof Buffer && audioStarted) {
        chunks.push(data);
      }
    });

    ws.addEventListener("close", () => {
      clearTimeout(timer);
      if (chunks.length) resolve(Buffer.concat(chunks));
      else reject(new Error("no_audio"));
    });
    ws.addEventListener("error", (e) => {
      clearTimeout(timer);
      reject(e);
    });
  });
}

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(405).json({ error: "method_not_allowed" });
    return;
  }
  let body;
  try {
    body = typeof req.body === "string" ? JSON.parse(req.body) : req.body;
  } catch (e) {
    res.status(400).json({ error: "bad_json" });
    return;
  }
  const text = (body && body.text ? String(body.text) : "").trim();
  if (!text) {
    res.status(400).json({ error: "empty_text" });
    return;
  }
  const speaker = (body && body.speaker) || "en-IN-PrabhatNeural";

  try {
    const audio = await synthesize(text, speaker);
    res.setHeader("Content-Type", "audio/mpeg");
    res.setHeader("Cache-Control", "no-store");
    res.status(200).send(audio);
  } catch (e) {
    console.error("TTS error:", e && e.message);
    res.status(502).json({ error: "tts_failed", detail: String(e && e.message) });
  }
};
