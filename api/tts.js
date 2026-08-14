// LUCIFER TTS proxy — runs on Vercel serverless (NOT the browser).
// The frontend POSTs {text} here; we call Sarvam (shubh, Indian MALE, hi-IN)
// server-side using the key from Vercel env (SARVAM_API_KEY) so it NEVER
// reaches the client. Cross-platform: works on web / Android WebView /
// iOS WKWebView because the browser only ever receives audio bytes.
module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    res.statusCode = 405;
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ error: "use POST" }));
    return;
  }
  let body;
  try {
    body = typeof req.body === "string" ? JSON.parse(req.body) : req.body;
  } catch (_) {
    body = {};
  }
  const text = (body && body.text) || "";
  if (!text || !text.trim()) {
    res.statusCode = 400;
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ error: "empty text" }));
    return;
  }

  const key = process.env.SARVAM_API_KEY;
  if (!key) {
    res.statusCode = 500;
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ error: "SARVAM_API_KEY not set on Vercel" }));
    return;
  }

  try {
    const r = await fetch("https://api.sarvam.ai/text-to-speech", {
      method: "POST",
      headers: {
        "api-subscription-key": key,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        text: text,
        target_language_code: "hi-IN",
        speaker: process.env.SARVAM_SPEAKER || "shubh",
        model: "bulbul:v3",
        output_audio_codec: "mp3",
      }),
    });
    if (!r.ok) {
      const detail = await r.text().catch(() => "");
      res.statusCode = 502;
      res.setHeader("content-type", "application/json");
      res.end(JSON.stringify({ error: "sarvam_upstream", status: r.status, detail: detail.slice(0, 200) }));
      return;
    }
    const payload = await r.json();
    const audios = payload.audios || [];
    if (!audios.length) {
      res.statusCode = 502;
      res.setHeader("content-type", "application/json");
      res.end(JSON.stringify({ error: "sarvam_no_audio" }));
      return;
    }
    // Sarvam returns base64 mp3; decode and stream raw bytes to the browser.
    const buf = Buffer.from(audios[0], "base64");
    res.statusCode = 200;
    res.setHeader("content-type", "audio/mpeg");
    res.setHeader("cache-control", "no-store");
    res.end(buf);
  } catch (e) {
    res.statusCode = 502;
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ error: "tts_proxy_failed", detail: String(e) }));
  }
};
