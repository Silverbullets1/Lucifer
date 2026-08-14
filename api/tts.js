// LUCIFER TTS proxy — forwards to the backend VPS which does the actual
// synthesis (Sarvam shubh + Edge PrabhatNeural fallback). The browser calls
// /api/tts (same-origin, no mixed content); we forward to VPS:8000.

const VPS_BASE = process.env.VPS_BASE || "http://152.67.14.127:8000";

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(405).json({ error: "method_not_allowed" });
    return;
  }
  try {
    const body = typeof req.body === "string" ? req.body : JSON.stringify(req.body);
    const upstream = await fetch(VPS_BASE + "/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    const buf = Buffer.from(await upstream.arrayBuffer());
    res.setHeader("Content-Type", "audio/wav");
    res.setHeader("Cache-Control", "no-store");
    res.status(upstream.status).send(buf);
  } catch (e) {
    console.error("TTS proxy error:", e && e.message);
    res.status(502).json({ error: "tts_proxy_failed" });
  }
};
