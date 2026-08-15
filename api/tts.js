// LUCIFER TTS proxy — forwards to the backend VPS which does the actual
// synthesis (Sarvam shubh + Edge PrabhatNeural fallback). The browser calls
// /api/tts (same-origin, no mixed content); we forward to the VPS backend on
// port 8000 and stream the mp3 back. TTS logic stays 100% on the backend.
const BACKEND = "http://152.67.14.127:8000/tts";

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(405).json({ error: "method_not_allowed" });
    return;
  }
  try {
    const upstream = await fetch(BACKEND, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body || {}),
    });
    if (!upstream.ok) {
      res.status(upstream.status).json({ error: "tts_upstream_failed" });
      return;
    }
    // Trust the backend's sniffsed Content-Type (mp3 from Sarvam, wav from fallbacks).
    const ct = upstream.headers.get("content-type") || "application/octet-stream";
    res.setHeader("Content-Type", ct);
    res.setHeader("Cache-Control", "no-store");
    const buf = Buffer.from(await upstream.arrayBuffer());
    res.status(200).send(buf);
  } catch (e) {
    res.status(502).json({ error: "tts_proxy_error", detail: String(e) });
  }
};
