// Relay from the library page (behind Cloudflare Access + host check in ../_middleware.js) to the VM control
// service: Access service token + HMAC-SHA256(secret, ts + method + path).
async function relay(env, method, path) {
  const ts = Math.floor(Date.now() / 1000).toString();
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(env.CONTROL_SECRET),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(ts + method + path));
  const sig = [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");
  const res = await fetch("https://router-control.walter-ai.cloud" + path, {
    method,
    headers: { "User-Agent": "Mozilla/5.0 (walter-library relay)", "CF-Access-Client-Id": env.CF_ACCESS_CLIENT_ID, "CF-Access-Client-Secret": env.CF_ACCESS_CLIENT_SECRET,
               "X-Walter-Ts": ts, "X-Walter-Sig": sig },
  });
  return new Response(await res.text(), { status: res.status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
}
export const onRequestPost = ({ env }) => relay(env, "POST", "/run");
