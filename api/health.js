const VPS_BASE = "http://152.67.14.127:8000";
module.exports = async (req, res) => {
  try {
    const target = VPS_BASE + "/health";
    const up = await fetch(target, { method: "GET", redirect: "manual" });
    const status = up.status;
    const body = await up.text();
    res.statusCode = status;
    res.setHeader("content-type", "application/json");
    res.end(body);
  } catch (e) {
    res.statusCode = 502;
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({ error: String(e), stack: e.stack }));
  }
};
