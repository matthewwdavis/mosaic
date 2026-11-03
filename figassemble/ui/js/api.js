// Calls into the Python engine over the local JSON-RPC endpoint.

const BASE = location.pathname.replace(/ui\/[^/]*$/, "");
// This window's number: the app's windows share one engine, which needs to know which is asking
const WIN = new URLSearchParams(location.search).get("win");

export async function rpc(method, ...args) {
  const res = await fetch(`${BASE}rpc`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ method, args, win: WIN }),
  });
  const data = await res.json();
  if (data.error) {
    console.error(data.trace || data.error);
    throw new Error(data.error);
  }
  return data.result;
}

const EXT = { pdf: "pdf", svg: "svg", png: "png", jpeg: "jpg", tiff: "tif" };

// URL of a variant's preview: SVG/PNG/JPEG as stored, PDFs rendered at `scale` x 72 dpi
export function assetUrl(variant, scale = 2, page = 0) {
  const base = `${BASE}asset/${variant.sha256}.${EXT[variant.kind]}`;
  return variant.kind === "pdf" ? `${base}?page=${page}&scale=${scale}` : base;
}
