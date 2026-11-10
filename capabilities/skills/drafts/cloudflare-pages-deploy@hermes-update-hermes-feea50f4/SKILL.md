---
name: cloudflare-pages-deploy
description: Deploy static sites to Cloudflare Pages via wrangler CLI with API token authentication. Includes project creation and custom domain setup.
---

# Cloudflare Pages Deployment

## Private-source safety gate

For an existing private or restricted site, read [Private Pages access](references/private-pages-access.md) before any upload. Prove production and deployment-alias protection using non-private canary bytes; never assume preview-only protection covers production. If no safe private route is available, prepare locally without publishing.

## When to use
- Deploying static HTML/CSS/JS sites
- Landing pages for SaaS products
- Quick static site hosting with CDN

## Steps

### 1. Required token permissions
The API token needs:
- `Account → Cloudflare Pages → Edit`
- Scoped API tokens for Zone.DNS.Edit are NOT enough for Pages

### 2. Create project (first time only)
```python
import json, urllib.request

token = "cfut_..."
account_id = "..."

payload = json.dumps({
    "name": "my-project",
    "production_branch": "main"
}).encode()

req = urllib.request.Request(
    f"https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects",
    data=payload, method="POST",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
)
with urllib.request.urlopen(req, timeout=15) as resp:
    project = json.loads(resp.read())

# Result: project["result"]["subdomain"] = "my-project.pages.dev"
```

### 3. Deploy with wrangler
```bash
CLOUDFLARE_API_TOKEN=cfut_... \
CLOUDFLARE_ACCOUNT_ID=... \
npx wrangler pages deploy /path/to/static/files --project-name my-project
```

### 4. Add custom domain
```python
# Add domain to Pages project
payload = json.dumps({"name": "app.example.com"}).encode()
req = urllib.request.Request(
    f"https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects/my-project/domains",
    data=payload, method="POST",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
)
with urllib.request.urlopen(req, timeout=15) as resp:
    result = json.loads(resp.read())

# Also create CNAME DNS record pointing to subdomain.pages.dev
```

## Writing Large HTML Files: Avoid `write_file` for HTML

**CRITICAL: The `write_file` tool corrupts large HTML files by injecting line-number prefixes into the document body.** The corrupted output looks like:

```
     1|     1|     1|<!DOCTYPE html>
     2|     2|     2|<html lang="fr">
```

This repeats on every single line. The result: browser shows plain text with no layout/CSS, completely broken site. Additionally, `write_file` fails silently or produces garbled output when HTML contains emoji characters (surrogate pairs).

**Safe methods for writing HTML:**
1. **Python script** — Write a `.py` script via `write_file`, then run it with `execute_code`. The script writes the HTML using Python's native file I/O.
2. **Terminal heredoc** — Use `cat > file.html << 'EOF' ... EOF` via `terminal`.
3. **Small patches** — For minor edits (changing one price, swapping one image src), the `patch` tool is safe — it only modifies the targeted string.

**Rule:** If the HTML file is >2KB, NEVER use `write_file` to write it directly. Always use a Python script or heredoc. The `patch` tool is safe for small string replacements regardless of file size.

## Cache Poisoning from Corrupted HTML Deployments

If a deployment uploads a corrupted HTML file (truncated, mangled DOCTYPE, or broken CSS), subsequent deploys may serve the broken version even after fixing. Symptoms: **page renders as plain black text on white background with no layout**, but `curl` shows the HTML is correct.

**Root causes observed:**
- `write_file` tool corrupting large HTML by injecting line numbers into the document body (e.g. `1|     1|     1|<!DOCTYPE html>`)
- Emoji/surrogate characters causing `write_file` to write garbled output
- The fix must be: write HTML via a **Python script** (use `write_file` for the script, then `execute_code` to run it) or via heredoc in `terminal`

**Resolution:**
1. Verify the deployed file matches your source: `curl -s <url> | head -5`
2. If deployed HTML is corrupted, fix the source file and redeploy with `rm -rf .wrangler` to force a full upload
3. If curl shows correct HTML but the browser shows broken layout, it's a browser cache issue — tell user to Ctrl+Shift+R
4. If curl itself shows corrupted HTML (line numbers, BOM, malformed DOCTYPE), the file was corrupted during write — rewrite via Python script or terminal heredoc

## Discovering Existing Cloudflare Architecture

Before deploying a landing page for an existing project, discover the full Cloudflare setup:
1. **List Pages projects** via API: `GET /accounts/{account_id}/pages/projects` — check names, subdomains, and custom domains.
2. **List Workers** via API: `GET /accounts/{account_id}/workers/scripts` — a project may have a Worker handling API/auth with a separate Pages frontend.
3. **List D1 databases**: `GET /accounts/{account_id}/d1/database` — check if the project has a database binding.
4. **List R2 buckets**: `GET /accounts/{account_id}/r2/buckets` — for media/file storage.
5. **Check wrangler.toml** in the project source for bindings and routes.

A "landing page rebuild" may need to integrate with the Worker's API endpoints (auth, Stripe, etc.), not just be a static file. Always ask if the user wants the landing connected to the existing backend.

**API token in curl**: When passing tokens with special characters via terminal, prefer writing a small Python script (`write_file` + `execute_code`) to avoid shell quoting nightmares. Bash heredoc also works for single commands.

## Related Skills and References

- **[Working with Existing Projects](references/working-with-existing-projects.md)** — When the user says "the project exists", follow this discovery and integration workflow to avoid creating duplicates.
- **[Production verification](references/production-verification.md)** — Verify the canonical production deployment, all static asset hashes, and the live app; distinguish client-specific HTTP failures from deployment failures.

## Pitfalls
- **TUI URL display** — Cloudflare Pages URLs are long and may be hard to read in the Hermes TUI. After deploying:
  - Provide the URL in plain text without markdown formatting (no `[text](url)` or `**bold**`)
  - Do NOT automatically send to Telegram unless user explicitly asks
  - If user complains about truncated URLs, offer to send via Telegram as a solution
  - Example: `fakerich-ai.pages.dev` not `**fakerich-ai.pages.dev**`
- **`[ERROR] Authentication error [code: 10000]`** — token lacks Pages permission. Add `Account → Cloudflare Pages → Edit`
- **`Project not found`** — must create project first via API before deploying
- **"Uploaded 0 files"** — file hash hasn't changed; `touch` the file to force re-upload
- **Custom domain status `pending`** — wait for SSL certificate provisioning (usually < 1 min)
- **Wrangler uses `CLOUDFLARE_API_TOKEN` env var** — not `CLOUDFLARE_API_KEY`
- **Browser cache hides updates after deploy** — Cloudflare Pages serves with `cache-control: max-age=14400` (4h). Always append cache-busting query params to asset URLs (e.g. `style.css?v=2`) OR tell the user to hard-refresh (Ctrl+Shift+R / Cmd+Shift+R). Verify with `curl -s <url>` to confirm the new content is served.
- **CDN edge cache persists beyond browser cache** — Even with `?v=2` query params, Cloudflare's edge cache may serve stale content for up to 4 hours. For guaranteed freshness, either: (a) change the actual filename (`style.a1b2.css`), (b) purge the zone cache via CF API (`POST /zones/{zone_id}/purge_cache`), or (c) add `Cache-Control: no-cache` headers via a Pages Function. After deploy, verify with `curl -s <url> | head` before telling the user it's live.
- **Deploying to the wrong project name** — When multiple Pages projects exist (e.g. `scena`, `scena-portal`, `scena-admin`), always verify which project owns the target custom domain before running `wrangler pages deploy`. Check via API: `GET /accounts/{account_id}/pages/projects` and inspect `domains`. Deploying to the wrong project uploads files successfully but the custom domain won't reflect the change. This is a silent failure — the deploy succeeds, but the user sees stale content on their branded URL.
- **`read_file`/`patch` corrupt HTML files** — The `read_file` tool and `patch` output prepend invisible line numbers to every line (like `     1|<!DOCTYPE html>`). If you read a file via `read_file`, modify it, and write it back via `write_file`, ALL HTML FILES WILL BE CORRUPTED. CSS won't parse, JS won't run, the site is broken. NEVER use `read_file` output to write HTML back to disk. Use `execute_code` with Python `open()` or `terminal` with `cat > file` instead.
- **`write_file` silently truncates large payloads** — HTML files 20KB+ may be silently truncated. Always verify written file size matches expected content size after `write_file`.
- **For editing HTML: use `execute_code`** — Build HTML content as a Python string and write directly with Python's `open(filepath, 'w')`. Never use `read_file`/`patch`/`write_file` for HTML files.
- **Stale content on main `*.pages.dev` URL after deploy** — Cloudflare Pages may keep serving an old deployment version on `project.pages.dev` even after a new deploy succeeds. The new content is always available at `https://<commit-hash>.pages.dev` (each deploy gets a unique hash URL). Always verify with `curl -s <url> | head -300` targeting the NEW deployment hash URL to confirm content. If the main URL still serves old content, it will self-propagate within minutes. Give the user the specific hash URL as the immediate solution, plus the main URL with a note to hard-refresh (Ctrl+Shift+R).
- **`read_file` CORRUPTS HTML files** — The `read_file` tool injects line-number prefixes into every line (e.g., `     1|<!DOCTYPE html>\n     2|<html>`). If that output is written back to the file via `patch` or `write_file`, the HTML becomes corrupted and browsers can't parse it. **NEVER use `read_file` on HTML files then write the content back.** Instead: (a) use `terminal` with `head`/`grep`/`cat` to inspect files (these return clean content), (b) use `write_file` to write complete HTML from scratch, (c) if you must patch, use `read_file` ONLY to identify the `old_string` (a short unique substring), then call `patch` — the patch tool handles line numbers correctly internally. If an HTML file is already corrupted, clean it with: `re.match(r'^\s*\d+\|(.*)', line)` to strip line-number prefixes from every line before rewriting.
- **Corrupt HTML is indistinguishable from CSS issues** — When `read_file` corrupts an HTML file, it still deploys successfully (wrangler just uploads garbage text). Pages load as unstyled text or blank. Always verify a freshly-deployed HTML file starts with `<!DOCTYPE html>` (no line numbers) by running `curl -s <url> | head -3` or `head -3 /path/to/index.html` before telling the user it works.
- **Deploying to the wrong project name** — When multiple Pages projects exist (e.g. `scena`, `scena-portal`, `scena-admin`), always verify which project owns the target custom domain before running `wrangler pages deploy`. Check via API: `GET /accounts/{account_id}/pages/projects` and inspect `domains`. Deploying to the wrong project uploads files successfully but the custom domain won't reflect the change. This is a silent failure — the deploy succeeds, but the user sees stale content on their branded URL.
- **`.html` links get 308-redirected and strip query parameters** — Cloudflare Pages serves `/foo.html` and `/foo` as the same content, but requests to `/foo.html` receive HTTP 308 → `/foo`. The 308 redirect DROPS query parameters and fragment hashes on some clients, which breaks any flow that relies on URL params (OAuth state, modal-open flags like `?signin=1`, tracking UTMs, anchor links to specific tabs). **Always link to the extensionless path** (`href="/login"`, not `href="/login.html"`). For OAuth flows, link directly to the backend endpoint (`https://api.example.com/api/auth/google`) rather than to a frontend page that bounces. Verify with: `curl -sI https://site/page.html | grep -i location` — if it shows a 308, the link is wrong.
- **Do not create backup files inside the directory being deployed** — `wrangler pages deploy pages/admin` uploads/serves everything under that folder, and unknown paths can also fall back to the current `index.html`. Keep backups in `/tmp`, outside the Pages source dir, or name them in a non-deployed workspace. After a cleanup deploy, verify the intended custom domain and hash URL contain the new strings.
- **`wrangler pages deploy` may serve stale HTML after repeated deploys** — Cloudflare Pages caches aggressively. If the HTML appears broken (line numbers showing, corrupted content) after a deploy that should have worked, it's likely the `write_file` tool corrupting HTML files by injecting line-number prefixes (e.g. `     1|     1|     1|<!DOCTYPE html>`). **Fix:** Write HTML using a Python `write_file` call or the `terminal` heredoc, NOT `execute_code` with inline Python string concatenation. After fixing, `rm -rf .wrangler` before re-deploying.
