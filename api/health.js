const { proxy } = require("../_proxy.js");
module.exports = (req, res) => proxy(req, "health");
