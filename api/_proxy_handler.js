const VPS_BASE = "http://152.67.14.127:8000";
const BLOCKED = new Set(["transfer-encoding", "connection", "content-encoding", "content-length"]);

export default async function handler(req, res) {
  // Determine upstream path from the function path
  const url = new URL(req.url, "http://localhost");
  let path = url.pathname;
  // Strip the /api prefix if present (depends on routing)
  path = path.replace(/^\/api\/?/, "");
  const target = VPS_BASE + "/" + path + url.search;

  const headers = {};
  for (const [k, v] of Object.entries(req.headers)) {
    if (k.toLowerCase() === "host" || k.toLowerCase() === "connection") continue;
    headers[k] = v;
  }

  let body;
  if (req.method === "GET" || req.method === "HEAD") body = undefined;
  else {
    const buf = await req.arrayBuffer?.();
    body = buf ? Buffer.from(buf) : undefined;
  }

  try {
    const up = await fetch(target, { method: req.method, headers, body, redirect: "manual" });
    const outHeaders = {};
    up.headers.forEach((v, k) => { if (!BLOCKED.has(k.toLowerCase())) outHeaders[k] = v; });
    const buf = Buffer.from(await up.arrayBuffer());
    return new Response(buf, { status: up.status, headers: outHeaders });
  } catch (e) {
    return new Response(JSON.stringify({ error: "VPS unreachable", detail: String(e) }), {
      status: 502,
      headers: { "content-type": "application/json" },
    });
  }
}
