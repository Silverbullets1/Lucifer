// LUCIFER voice proxy — forwards mic audio to the backend VPS /voice endpoint
// (STT: OpenAI Whisper via Nous free gateway + LLM). The browser calls
// /api/voice (same-origin); we forward multipart audio to VPS:8000.
const BACKEND = "http://152.67.14.127:8000/voice";

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(405).json({ error: "method_not_allowed" });
    return;
  }
  try {
    const upstream = await fetch(BACKEND, {
      method: "POST",
      headers: { "Content-Type": req.headers["content-type"] || "multipart/form-data" },
      body: req.body,
    });
    const txt = await upstream.text();
    res.setHeader("Content-Type", "application/json");
    res.status(upstream.status).send(txt);
  } catch (e) {
    res.status(502).json({ error: "voice_proxy_error", detail: String(e) });
  }
};
