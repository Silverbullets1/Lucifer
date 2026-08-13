// Vercel serverless proxy: forwards /api/* to backend, preserving method + body + query.
// Fix: renamed catch-all param from 'path' (Vercel reserved -> 404) to 'slug'.
const BACKEND = "https://gone-verification-cinema-citizen.trycloudflare.com";

export default async function handler(req) {
  const slug = req.query.slug || [];
  const path = "/" + slug.join("/");
  const qs = req.url.includes("?") ? req.url.slice(req.url.indexOf("?")) : "";
  const target = BACKEND + path + qs;

  const headers = {};
  for (const [k, v] of Object.entries(req.headers)) {
    const lk = k.toLowerCase();
    if (lk === "host" || lk === "content-length") continue;
    headers[k] = v;
  }

  const init = { method: req.method, headers };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = typeof req.body === "string" ? req.body : JSON.stringify(req.body);
  }

  const r = await fetch(target, init);
  const buf = Buffer.from(await r.arrayBuffer());
  return new Response(buf, {
    status: r.status,
    headers: { "content-type": r.headers.get("content-type") || "application/json" },
  });
}
