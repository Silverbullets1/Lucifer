const VPS_BASE = "http://152.67.14.127:8000";
async function proxy(req, res, path) {
  const query = req.url.includes("?") ? "?" + req.url.split("?")[1] : "";
  const target = VPS_BASE + path + query;
  const headers = {};
  for (const [k, v] of Object.entries(req.headers)) {
    if (["host", "connection"].includes(k.toLowerCase())) continue;
    headers[k] = v;
  }
  let body;
  if (req.method === "GET" || req.method === "HEAD") body = undefined;
  else body = await new Promise((resolve) => {
    const chunks = []; req.on("data", (c) => chunks.push(c)); req.on("end", () => resolve(Buffer.concat(chunks)));
  });
  try {
    const up = await fetch(target, { method: req.method, headers, body });
    const out = {}; up.headers.forEach((v, k) => { if (!["transfer-encoding","connection","content-encoding"].includes(k.toLowerCase())) out[k]=v; });
    res.status(up.status); for (const [k,v] of Object.entries(out)) res.setHeader(k, v);
    res.send(Buffer.from(await up.arrayBuffer()));
  } catch (e) { res.status(502).json({ error: "VPS unreachable", detail: String(e) }); }
}
module.exports = { proxy };
