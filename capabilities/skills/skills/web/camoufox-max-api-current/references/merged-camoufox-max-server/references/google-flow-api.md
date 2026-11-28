# Google Flow API — Internal Endpoint Discovery

Flow (labs.google/fx/tools/flow) is a React SPA that calls internal Google APIs.
When the web UI is too fragile (Camoufox `/tab/click` and `/tab/type` timeout),
use network interception to discover and call these APIs directly with cookies.

## Strategy

1. Create a Camoufox tab, inject Google cookies
2. Inject a `fetch`/`XHR` monkey-patch via `/tab/evaluate` BEFORE navigation
3. Navigate to Flow, perform the generation action
4. Read `window.__flowApiCalls` to see the real API endpoints
5. Call those endpoints directly via Python `requests` with the same cookies

## Monkey-Patch Script

```javascript
// Inject BEFORE navigating to Flow
window.__flowApiCalls = [];
(function(){
  var origFetch = window.fetch;
  window.fetch = function(url, opts) {
    opts = opts || {};
    var entry = {
      url: typeof url === 'string' ? url : url.url,
      method: (opts.method || 'GET').toUpperCase(),
      body: typeof opts.body === 'string' ? opts.body.substring(0, 3000) : null,
      headers: JSON.stringify(opts.headers || {}).substring(0, 800),
      ts: Date.now()
    };
    window.__flowApiCalls.push(entry);
    return origFetch.apply(this, arguments);
  };
  // Also patch XMLHttpRequest
  var origOpen = XMLHttpRequest.prototype.open;
  var origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url) {
    this.__flowUrl = url;
    this.__flowMethod = method;
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function(body) {
    if (this.__flowUrl) {
      window.__flowApiCalls.push({
        url: this.__flowUrl,
        method: this.__flowMethod,
        body: typeof body === 'string' ? body.substring(0, 3000) : null,
        ts: Date.now()
      });
    }
    return origSend.apply(this, arguments);
  };
})();
```

## Flow Model Comparison

| Model | Duration | Audio | API Access | Quality |
|---|---|---|---|---|
| **Omni Flash** | 4s/6s/8s/**10s** | ✅ Native | Flow API only | Standard |
| Veo 3.1 Quality | 8s max | ❌ Gemini API | Gemini API (`veo-3.1-generate-preview`) | Highest |
| Veo 3.1 Fast | 8s max | ❌ Gemini API | Gemini API (`veo-3.1-fast-generate-preview`) | Good |
| Veo 3.1 Lite | 8s max | ❌ Gemini API | Gemini API (`veo-3.1-lite-generate-preview`) | Fast |

**Key insight**: `generateAudio` is NOT supported in Gemini API for ANY Veo model.
Audio works ONLY through the Flow web interface (Omni Flash) or Vertex AI.
If audio + 10s duration are required, Omni Flash via Flow is the only option.

## UseAPI.net Pattern (Third-Party Proxy)

The useapi.net service acts as a proxy: clients provide their Google Flow cookies,
and useapi.net calls Google's internal Flow API. The endpoints they proxy:

- `POST /v1/google-flow/videos` — submit a video generation job
- `GET /v1/google-flow/jobs/{jobId}` — poll job status
- `POST /v1/google-flow/assets/` — upload reference images

The actual Google internal endpoints remain undiscovered — use the monkey-patch
approach above to capture them directly from the browser.
