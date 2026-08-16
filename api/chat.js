// Proxy /api/chat to VPS backend (non-streaming)
const BACKEND = "http://152.67.14.127:8000/chat";

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
    const txt = await upstream.text();
    res.setHeader("Content-Type", "application/json");
    res.status(upstream.status).send(txt);
  } catch (e) {
    res.status(502).json({ error: "chat_proxy_error", detail: String(e) });
  }
};
