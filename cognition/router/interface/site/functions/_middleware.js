// walter-library: only served on the instance's library host (__LIBRARY_HOST__, filled at build from host.json),
// which Cloudflare Access protects (the owner only).
// The *.pages.dev addresses cannot be put behind Access (not in the zone): they answer 404.
export async function onRequest(context) {
  const host = new URL(context.request.url).hostname;
  if (host !== "__LIBRARY_HOST__" || !context.request.headers.get("Cf-Access-Jwt-Assertion")) {
    return new Response("Not found", { status: 404, headers: { "Cache-Control": "no-store" } });
  }
  const res = await context.next();
  const out = new Response(res.body, res);
  out.headers.set("Cache-Control", "no-store");
  out.headers.set("X-Robots-Tag", "noindex, nofollow");
  return out;
}
