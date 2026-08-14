module.exports = async (req, res) => {
  const info = {
    method: req.method,
    hasOn: typeof req.on,
    hasArrayBuffer: typeof req.arrayBuffer,
    url: req.url,
    headersType: typeof req.headers,
  };
  res.statusCode = 200;
  res.setHeader("content-type", "application/json");
  res.end(JSON.stringify(info));
};
