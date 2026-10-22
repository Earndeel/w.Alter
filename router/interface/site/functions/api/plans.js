// Plan edits from the library page (behind Cloudflare Access + host check in ../_middleware.js) to the VM control
// service: Access service token + HMAC-SHA256(secret, ts + method + path + sha256(body)).
async function hex(buf) { return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join(""); }
export async function onRequestPost({ request, env }) {
  const body = await request.text();
  if (body.length > 4000) return new Response(JSON.stringify({ error: "too large" }), { status: 413 });
  const ts = Math.floor(Date.now() / 1000).toString();
  const digest = await hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(body)));
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(env.CONTROL_SECRET),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await hex(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(ts + "POST" + "/plans" + digest)));
  const res = await fetch("__CONTROL_ORIGIN__" + "/plans", {
    method: "POST", body,
    headers: { "User-Agent": "Mozilla/5.0 (walter-library relay)", "Content-Type": "application/json",
               "CF-Access-Client-Id": env.CF_ACCESS_CLIENT_ID, "CF-Access-Client-Secret": env.CF_ACCESS_CLIENT_SECRET,
               "X-Walter-Ts": ts, "X-Walter-Sig": sig },
  });
  return new Response(await res.text(), { status: res.status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
}
