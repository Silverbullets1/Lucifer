// Vercel serverless proxy: forwards /api/* to backend, preserving method + body + headers.
// This avoids Vercel rewrite's POST-body-drop bug.
const BACKEND = "https://gone-verification-cinema-citizen.trycloudflare.com";

export default async function handler(req, res) {
  const path = req.query.path ? req.query.path.join("/") : "";
  const url = `${BACKEND}/${path}`;
  const method = req.method;
  const headers = {};
  const ct = req.headers["content-type"];
  if (ct) headers["Content-Type"] = ct;
  let body;
  if (method !== "GET" && method !== "HEAD") {
    body = req.read ? await getRawBody(req) : undefined;
  }
  try {
    const r = await fetch(url, { method, headers, body });
    const buf = Buffer.from(await r.arrayBuffer());
    res.setHeader("Content-Type", r.headers.get("content-type") || "application/json");
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.status(r.status).send(buf);
  } catch (e) {
    res.status(502).json({ error: "backend unreachable", detail: String(e) });
  }
}

function getRawBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}
