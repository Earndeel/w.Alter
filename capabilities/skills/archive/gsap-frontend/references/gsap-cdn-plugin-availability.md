# GSAP Plugin CDN Availability

## Public CDN (jsdelivr / unpkg)

These plugins are served from `https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/`:

| Plugin | CDN | Notes |
|--------|-----|-------|
| gsap (core) | ✅ | Base package |
| ScrollTrigger | ✅ | |
| ScrollToPlugin | ❌ | npm only |
| Flip | ✅ | |
| MotionPathPlugin | ✅ | |
| Observer | ✅ | |
| Draggable | ✅ | |
| CustomEase | ❌ | npm only |
| EasePack | ✅ | |
| TextPlugin | ✅ | Simple text replacement, NOT SplitText |

## npm Only (must copy from node_modules)

These plugins are in the `gsap` npm package (v3.13+) but NOT on public CDNs:

| Plugin | npm Path |
|--------|----------|
| SplitText | `node_modules/gsap/dist/SplitText.min.js` |
| ScrollSmoother | `node_modules/gsap/dist/ScrollSmoother.min.js` |
| ScrollToPlugin | `node_modules/gsap/dist/ScrollToPlugin.min.js` |
| ScrambleTextPlugin | `node_modules/gsap/dist/ScrambleTextPlugin.min.js` |
| MorphSVGPlugin | `node_modules/gsap/dist/MorphSVGPlugin.min.js` |
| DrawSVGPlugin | `node_modules/gsap/dist/DrawSVGPlugin.min.js` |
| CustomEase | `node_modules/gsap/dist/CustomEase.min.js` |
| InertiaPlugin | `node_modules/gsap/dist/InertiaPlugin.min.js` |

## Verified CDN Tests (May 2026)

```bash
# PASS
curl -sI "https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js" | head -1     # 200
curl -sI "https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/ScrollTrigger.min.js" | head -1 # 200
curl -sI "https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/Flip.min.js" | head -1    # 200
curl -sI "https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/MotionPathPlugin.min.js" | head -1 # 200

# FAIL (404)
curl -sI "https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/SplitText.min.js" | head -1  # 404
curl -sI "https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/ScrollSmoother.min.js" | head -1 # 404
curl -sI "https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/ScrambleTextPlugin.min.js" | head -1 # 404
```

## Workaround for Static Sites

```bash
npm install gsap@latest
mkdir -p dist/js/
cp node_modules/gsap/dist/*.min.js dist/js/
# Deploy dist/ to Cloudflare Pages
# Reference all plugins locally: <script src="js/SplitText.min.js"></script>
```

The files are small enough for Cloudflare Pages (largest: gsap.min.js ~73KB, ScrollSmoother ~13KB, total ~280KB for all 12+ plugins).
