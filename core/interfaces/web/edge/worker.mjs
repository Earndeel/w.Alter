// Edge worker (Cloudflare) in front of the public address of the W.Alter web interface.
// The interface signs a browser in with a SameSite=Strict cookie. A top-level page reached from another site — the
// Cloudflare Access login that precedes it, or a link opened from a chat — therefore arrives without that cookie and
// the interface answers 401 although the browser is signed in. For exactly that case (GET navigation, initiated by
// another site, refused with 401) the worker answers with a page that reloads itself: the reload is initiated by the
// site itself, so the browser sends the Strict cookie. A browser that is really not signed in gets the 401 on that
// reload (same-origin), so there is no loop. Every other request and answer passes through untouched.
// Runs after Cloudflare Access; holds no secret and no instance data.

const RELOAD = '<!doctype html><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
  + '<meta http-equiv="refresh" content="0"><title>…</title><body style="background:#000"></body>';

export async function handle(request, origin) {
  const response = await origin(request);
  const crossSite = ['cross-site', 'same-site'].includes(request.headers.get('sec-fetch-site') || '');
  if (response.status === 401 && request.method === 'GET' && crossSite
      && request.headers.get('sec-fetch-mode') === 'navigate') {
    return new Response(RELOAD, { status: 200, headers: {
      'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store', 'referrer-policy': 'no-referrer' } });
  }
  return response;
}

export default { fetch: (request) => handle(request, (r) => fetch(r)) };
