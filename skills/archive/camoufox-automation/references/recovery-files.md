# Recovery files for camoufox-max

When the directory has been stripped of everything but `server-max.js`, drop these two files back in place before running `npm install --no-audit --no-fund`. Verified 2026-06-06.

## package.json

```json
{
  "name": "camoufox-max",
  "version": "1.0.0",
  "main": "server-max.js",
  "scripts": {
    "start": "node server-max.js"
  },
  "dependencies": {
    "camoufox-js": "^0.8.5",
    "playwright-core": "^1.48.0",
    "express": "^4.21.0",
    "dotenv": "^16.4.5"
  }
}
```

The version pins are the ones that worked on the W.Alter VPS. Newer minor versions typically work, but lock to these if you hit module resolution errors.

## lib/macros.js

`server-max.js` requires `expandMacro` from `./lib/macros`. The recovered stub is intentionally minimal — it only adds `https://` to a bare hostname. Original macro semantics (e.g. `@google_search`, `@youtube_search`) are not preserved here; if your workflow depends on them, restore from git history instead of using this stub.

```js
// Minimal stub — restores missing lib/macros module after checkout cleanup.
// Identity passthrough is safe — caller usually provides full URLs.
function expandMacro(url) {
  if (!url || typeof url !== 'string') return url;
  // Add scheme if user passed a bare host
  if (/^[a-z0-9-]+(\.[a-z0-9-]+)+/i.test(url) && !/^https?:\/\//i.test(url)) {
    return `https://${url}`;
  }
  return url;
}

module.exports = { expandMacro };
```

## Smoke test before service-ing it

```
cd /root/.hermes/camoufox-max
CAMOFOX_MAX_PORT=9377 node server-max.js
```

Expect: `Camoufox MAX server running on port 9377` then `humanize: 2.0, geoip: true, persistent_context: true`. If you see `Cannot find module 'camoufox-js'` the install failed — re-run `npm install` and confirm `node_modules/camoufox-js/package.json` exists.
