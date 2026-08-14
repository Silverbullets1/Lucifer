const VPS_BASE = "http://152.67.14.127:8000";
module.exports = async (req, res) => {
  try {
    const url = new URL(req.url, "http://localhost");
    const target = VPS_BASE + "/voice" + url.search;
    const headers = {};
    if (req.headers) for (const [k, v] of Object.entries(req.headers)) {
      if (k.toLowerCase() === "host" || k.toLowerCase() === "connection") continue;
      headers[k] = v;
    }
    let body;
    if (req.method === "GET" || req.method === "HEAD") body = undefined;
    else body = await new Promise((resolve) => {
      const chunks = []; req.on("data", (c) => chunks.push(c)); req.on("end", () => resolve(Buffer.concat(chunks)));
    });
    const up = await fetch(target, { method: req.method, headers, body, redirect: "manual" });
    res.statusCode = up.status;
    up.headers.forEach((v, k) => {
      const lk = k.toLowerCase();
      if (["transfer-encoding","connection","content-encoding","content-length"].includes(lk)) return;
      try { res.setHeader(k, v); } catch (_) {}
    });
    const buf = Buffer.from(await up.arrayBuffer());
    res.end(buf);
  } catch (e) {
    res.statusCode = 502;
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ error: "VPS unreachable", detail: String(e) }));
  }
};
