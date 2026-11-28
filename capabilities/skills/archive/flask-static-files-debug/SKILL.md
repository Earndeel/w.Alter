---
name: flask-static-files-debug
description: Debug and fix Flask static file 404s (CSS/JS not loading) in deployed apps, then apply modern UI redesign patterns.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Flask, DevOps, Static-Files, Debugging, UI-Refactor]
    related_skills: [scena-video-factory, flask-dashboard-pipeline, cloudflare-worker-deploy-curl]
---

## Trigger
Frontend of a Flask app deployed behind a tunnel/Cloudflare returns 404 for CSS/JS files, resulting in a degraded or broken UI. Need to diagnose path mismatches and optionally apply a modern UI redesign.

---

## 1 — Diagnose the static files mismatch

```bash
# 1.1 Fetch the live HTML to see what paths are referenced
curl -s https://<domain>/ | head -20

# 1.2 Test the referenced asset paths directly
curl -s -o /dev/null -w '%{http_code}' https://<domain>/<referenced-path>

# 1.3 Check Flask static configuration in app.py
# Look for: static_folder='static', static_url_path='/static'
# Default: static_url_path='/static' → assets served at /static/<file>
# If templates reference '/' instead of '/static/', they will 404.
```

**Common mismatch patterns:**
- `app = Flask(__name__, static_folder='static', static_url_path='/static')` ✓
- HTML references `/style.css` ✗ → should be `/static/style.css`
- HTML references `/app.js` ✗ → should be `/static/app.js`

---

## 2 — Locate the project files

```bash
# Find the running service's working directory
systemctl status <service-name> --no-pager -l
# Look for: Main PID and the command line (e.g., /root/projects/frame_lens/venv/bin/python app.py)

# Browse from there
ls -la /root/projects/frame_lens/
# Expected: app.py, static/, templates/
```

---

## 3 — Fix the template paths

Edit `templates/index.html` (or equivalent):

```html
<!-- WRONG -->
<link rel="stylesheet" href="/style.css"/>
<script src="/app.js"></script>

<!-- CORRECT -->
<link rel="stylesheet" href="/static/style.css"/>
<script src="/static/app.js"></script>
```

If you prefer to keep root-level paths, change Flask config:
```python
app = Flask(__name__, static_folder='static', static_url_path='')
# Now /style.css maps to static/style.css
```
But the `/static/` prefix is safer (avoids collisions).

---

## 4 — Verify locally before redeploy

```bash
# From project root, test Flask directly
source venv/bin/activate
python app.py
# In another shell:
curl -s http://localhost:5000/static/style.css | head -5  # should return CSS
curl -s http://localhost:5000/ | grep static/style.css  # should appear in HTML
```

---

## 5 — Restart the service

```bash
systemctl restart <service-name>
systemctl status <service-name> --no-pager -l  # confirm active
```

---

## 6 — (Optional) Modern UI Refactor Pattern

When the UI is functional but "degeulasse" (outdated/ugly), apply a premium dark theme in place:

### Design principles
- **Palette**: neutral dark base (#0a0a0b), raised surface (#18181b), single vibrant accent (indigo #6366f1)
- **Typography**: Inter for UI, JetBrains Mono for code blocks (via Google Fonts)
- **Spacing**: generous padding, mobile-first responsive breakpoints
- **Micro-interactions**: hover glow on dropzone, smooth progress transitions, copy-button feedback
- **JSON display**: syntax highlighting with key (blue), string (green), number (yellow), boolean (pink)

### File changes
1. **templates/index.html** — rewrite with SVG logo icon, clean semantic structure
2. **static/style.css** — full rewrite with CSS custom properties, animations, scrollbar styling
3. **static/app.js** — keep logic, add smooth progress simulation, improve copy feedback

### Validation
```bash
curl -s https://<domain>/static/style.css | wc -l  # should be >500 for modern CSS
curl -s https://<domain>/ | grep -i 'inter\|jetbrains'  # should show font links
```

---

## Pitfalls

- **Venv PATH issues**: When systemd runs Flask via a venv, PATH may missing `/usr/bin` for `ffmpeg`/`ffprobe`. Use absolute paths (`/usr/bin/ffprobe`) or `shutil.which()` checks.
- **CORS**: If frontend is on different domain (Pages) than API (tunnel), ensure `flask_cors.CORS(app)` is enabled.
- **Static cache**: Cloudflare may cache 404s. After fixing, purge cache or wait a few minutes.
- **Template selection**: Ensure Flask `template_folder` param points correctly; default is `templates/` in app root.
- **Static URL path**: Never leave `static_url_path` undefined if your HTML uses `/static/` references; Flask default is `/static` so it's safe to omit or set explicitly.

---

## Quick Decision Flow

```
Static files 404?
    ├─ Yes → curl https://domain/static/file.css
    │         ├─ 200 → paths correct, issue is Cloudflare cache (purge)
    │         └─ 404 → check Flask static_url_path vs template href
    │                  └─ mismatch? Fix template to /static/... or adjust Flask config
    └─ No  → UI still ugly? Apply Modern UI Refactor pattern above
---
