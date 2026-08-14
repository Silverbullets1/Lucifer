import { proxy } from "../_proxy.mjs";
export default (req, res) => proxy(req, res, "/health");
