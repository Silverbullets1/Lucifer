const VPS_BASE = "http://152.67.14.127:8000";
const BLOCKED = new Set(["transfer-encoding", "connection", "content-encoding", "content-length"]);

async function proxy(req, path) {
  const url = new URL(req.url, "http://localhost");
  const target = VPS_BASE + "/" + path + url.search;

  // Build upstream headers from Vercel req.headers (Headers object or plain)
  const headers = {};
  if (req.headers && typeof req.headers.forEach === "function") {
    req.headers.forEach((v, k) => { if (k.toLowerCase() !== "host" && k.toLowerCase() !== "connection") headers[k] = v; });
  } else if (req.headers) {
    for (const [k, v] of Object.entries(req.headers)) {
      if (k.toLowerCase() === "host" || k.toLowerCase() === "connection") continue;
      headers[k] = v;
    }
  }

  let body;
  if (req.method === "GET" || req.method === "HEAD") body = undefined;
  else {
    const buf = await req.arrayBuffer();
    body = buf.byteLength ? Buffer.from(buf) : undefined;
  }

  const up = await fetch(target, { method: req.method, headers, body, redirect: "manual" });
  const outHeaders = {};
  up.headers.forEach((v, k) => { if (!BLOCKED.has(k.toLowerCase())) outHeaders[k] = v; });
  const buf = Buffer.from(await up.arrayBuffer());
  return new Response(buf, { status: up.status, headers: outHeaders });
}

module.exports = { proxy };
