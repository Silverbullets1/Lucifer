// LUCIFER — Vercel serverless proxy: /api/* -> VPS:8000 (HTTP, server-side)
// Browser calls same-origin /api/chat/stream (HTTPS) -> this function -> VPS (HTTP).
// No Cloudflare tunnel, no mixed-content issue.

const VPS_BASE = "http://152.67.14.127:8000";

export default async function handler(req, res) {
  // strip leading "/api" from path
  const rawPath = req.url.split("?")[0].replace(/^\/api\/?/, "");
  const query = req.url.includes("?") ? "?" + req.url.split("?")[1] : "";
  const target = VPS_BASE + "/" + rawPath + query;

  const headers = {};
  // forward only safe headers; drop host
  for (const [k, v] of Object.entries(req.headers)) {
    if (k.toLowerCase() === "host" || k.toLowerCase() === "connection") continue;
    headers[k] = v;
  }

  let body;
  if (req.method === "GET" || req.method === "HEAD") {
    body = undefined;
  } else {
    // read raw body
    body = await new Promise((resolve) => {
      const chunks = [];
      req.on("data", (c) => chunks.push(c));
      req.on("end", () => resolve(Buffer.concat(chunks)));
    });
  }

  try {
    const upstream = await fetch(target, {
      method: req.method,
      headers,
      body,
    });

    // forward upstream status + headers (except hop-by-hop)
    const outHeaders = {};
    upstream.headers.forEach((v, k) => {
      if (["transfer-encoding", "connection", "content-encoding"].includes(k.toLowerCase())) return;
      outHeaders[k] = v;
    });
    res.status(upstream.status);
    for (const [k, v] of Object.entries(outHeaders)) res.setHeader(k, v);

    // stream body (Buffer)
    const buf = Buffer.from(await upstream.arrayBuffer());
    res.send(buf);
  } catch (e) {
    res.status(502).json({ error: "VPS unreachable", detail: String(e) });
  }
}
