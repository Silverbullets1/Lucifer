// LUCIFER TTS proxy — runs on Vercel serverless (NOT the browser).
// Uses Microsoft Edge TTS (edge-tts) with en-IN-PrabhatNeural — native Hindi,
// keyless, free. The frontend POSTs {text, speaker?} and we stream back mp3.
// No API keys needed (Edge TTS is keyless).

const { EdgeTTS } = require("edge-tts");

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
    const tts = new EdgeTTS();
    const chunks = [];
    const stream = tts.ttsStream(text, speaker);
    stream.on("data", (d) => chunks.push(d));
    await new Promise((resolve, reject) => {
      stream.on("end", resolve);
      stream.on("error", reject);
    });
    const audio = Buffer.concat(chunks);
    res.setHeader("Content-Type", "audio/mpeg");
    res.setHeader("Cache-Control", "no-store");
    res.status(200).send(audio);
  } catch (e) {
    console.error("TTS error:", e && e.message);
    res.status(502).json({ error: "tts_failed", detail: String(e && e.message) });
  }
};
