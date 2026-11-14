# HyperFrames Pitfalls & Troubleshooting

## ARM64 / aarch64 Render Failure (2026-05-11)

### Problem
HyperFrames downloads `chrome-headless-shell` for rendering, but the binary is **x86_64 only**. On ARM64 servers (AWS Graviton, Apple Silicon, Oracle Ampere), the render fails with:

```
/root/.cache/hyperframes/chrome/chrome-headless-shell/linux_arm-131.0.6778.85/.../chrome-headless-shell: 
Syntax error: word unexpected (expecting ")")
```

### Attempted fixes (all failed)

| Approach | Result |
|---|---|
| `PUPPETEER_EXECUTABLE_PATH` env var | Ignored by HyperFrames — uses own cache |
| `npx puppeteer browsers install chromium@latest --platform linux_arm` | Downloads x86_64 binary anyway (Puppeteer bug) |
| Replace cached binary with Puppeteer's Chromium | Chromium ≠ chrome-headless-shell format — still crashes |
| `--docker` flag | Docker image targets `linux/amd64`, fails on ARM64 host with `exec /bin/sh: exec format error` |

### Only known working solutions
1. **Render on x86_64 machine** (Intel/AMD server, not ARM)
2. **Use GitHub Actions CI** with `ubuntu-latest` runner for rendering
3. **Pre-built HyperFrames Docker image** with proper multi-arch support (not yet available)

### Preview-only mode works
The `npx hyperframes preview` server runs fine on ARM64 — only the render (Puppeteer + FFmpeg) fails. Use preview for composition development, render on x86_64. & Troubleshooting

## ARM64 Render Failure (Critical)

**Symptom:**
```bash
$ cd test-video && npx hyperframes render

/root/.cache/hyperframes/chrome/.../chrome-headless-shell: 6: ��: not found
/root/.cache/hyperframes/chrome/.../chrome-headless-shell: 11: Syntax error: word unexpected (expecting ")")

TROUBLESHOOTING: https://pptr.dev/troubleshooting
   Try --docker for containerized rendering
```

**Root cause:** HyperFrames downloads a Chrome headless-shell binary for the detected architecture. On ARM64 (aarch64) servers like Oracle Cloud Ampere, the downloaded binary may be x86_64, causing ELF incompatibility.

**Fix:**
1. Use Docker: `npx hyperframes render --docker` (if Docker available)
2. Render on an x86_64 machine instead
3. Check architecture: `uname -m` — if it's `aarch64`, expect this issue

**Session observed:** May 2026, Oracle Cloud ARM64 instance, Node 22, FFmpeg installed.

---

## Premium GSAP Plugins Not on Public CDN

**Problem:** `https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/SplitText.min.js` returns 404.

**Cause:** SplitText, ScrambleText, DrawSVG, MorphSVG, ScrollSmoother are NOT published to jsdelivr or unpkg.

**Solution A — Use npm (v3.13+):**
```bash
npm install gsap@latest
# Plugins are in node_modules/gsap/dist/
cp node_modules/gsap/dist/SplitText.min.js node_modules/gsap/dist/ScrollSmoother.min.js ...
```

**Solution B — Use only CDN-available plugins:**
ScrollTrigger, ScrollTo, Flip, MotionPath, Observer, Draggable, CustomEase, EasePack are on CDN.

**Verified working CDN plugins:**
```
https://unpkg.com/gsap@3.12.5/dist/Flip.min.js → 200 OK
https://unpkg.com/gsap@3.12.5/dist/MotionPathPlugin.min.js → 200 OK
```

**NOT working CDN (must use npm):**
```
https://unpkg.com/gsap@3.12.5/dist/SplitText.min.js → 404
https://unpkg.com/gsap@3.12.5/dist/ScrollSmoother.min.js → 404
https://unpkg.com/gsap@3.12.5/dist/ScrambleTextPlugin.min.js → 404
https://unpkg.com/gsap@3.12.5/dist/MorphSVGPlugin.min.js → 404
https://unpkg.com/gsap@3.12.5/dist/DrawSVGPlugin.min.js → 404
```

**Note:** The `gsap-skills` repo README states "Install everything from the public gsap npm package" — this is correct for npm but NOT for CDN distribution. The npm package v3.13+ includes all plugins; the CDN mirrors do not.

---

## Cloudflare Pages — Wrong Project Deploy

**Symptom:** Deployed to project "scena" but prod (custom domain) shows old content.

**Cause:** Custom domain `scena.walter-ai.cloud` was attached to project `scena-portal`, not `scena`. Deploying to `scena` only updates the `.pages.dev` subdomain.

**Fix:** Check which project owns the custom domain before deploying:
```bash
curl -s "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/pages/projects/$PROJECT" \
  -H "Authorization: Bearer $CF_TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['domains'])"
```

---

## HyperFrames Preview Server Access

The preview server runs on `http://localhost:3333` by default (or `--port`). To expose for remote viewing:

1. **Cloudflare Tunnel:** `cloudflared tunnel --url http://localhost:3333`
2. **Deploy as static site:** Copy the composition HTML to Cloudflare Pages (will show as web page, not rendered video)

Note: `cloudflared` may take 30-60s to provision the tunnel and produce the URL in stdout. Output arrives late.
