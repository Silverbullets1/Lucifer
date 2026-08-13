// Vercel serverless proxy (Node.js runtime): forwards /api/* to backend, preserving method+body+query.
// Node handler signature is (req, res) — NOT Web (Request => Response).
const BACKEND = "https://gone-verification-cinema-citizen.trycloudflare.com";

export default async function handler(req, res) {
  const slug = req.query.slug || [];
  const path = "/" + slug.join("/");
  const qs = req.url.includes("?") ? req.url.slice(req.url.indexOf("?")) : "";
  const target = BACKEND + path + qs;

  const headers = { ...req.headers };
  delete headers.host;
  delete headers["content-length"];

  const init = { method: req.method, headers };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = typeof req.body === "string" ? req.body : JSON.stringify(req.body ?? {});
  }

  try {
    const r = await fetch(target, init);
    const buf = Buffer.from(await r.arrayBuffer());
    res.status(r.status);
    const ct = r.headers.get("content-type");
    if (ct) res.setHeader("content-type", ct);
    res.send(buf);
  } catch (e) {
    res.status(502).send("proxy error: " + e.message);
  }
}
