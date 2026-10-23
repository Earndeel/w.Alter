# Pitfalls & Fixes — April 17, 2026

## Telegram formatTelegramHtml placeholder corruption
The formatter uses `__TG_HTML_N__` placeholders to protect supported HTML tags, then runs markdown-to-HTML conversions. If `__(.+?)__` (markdown underline bold) is included as a conversion pattern, it matches the `__` delimiters inside the placeholder itself and wraps them in `<b>` tags, corrupting the placeholder. Result: Telegram shows literal `TG_HTML_0`, `TG_HTML_3` etc. instead of formatted text.
**Fix**: remove the `__(.+?)__` -> `<b>` conversion line; `**text**` pattern handles markdown bold.

## ctx.waitUntil() does NOT survive CF Worker isolate lifecycle
For async jobs taking >30s (Fal.ai polling), `ctx.waitUntil(pollFalResult(...))` is unreliable — the isolate may be recycled before polling completes. The job stays stuck in `processing` forever with no error.
**Fix**: add cron-triggered sweeper (scheduled handler, every minute) that scans for `processing` jobs and polls the provider. Both video AND image jobs need cron fallback.

## Image jobs missing cron polling
Production had `processPendingFalVideoJobs` in cron but NO equivalent for images. Image async results were only handled by `ctx.waitUntil` which silently failed.
**Fix**: add `processPendingFalImageJobs` (polls Fal for jobs with request_id) and `cleanupStuckImageJobs` (auto-fails jobs stuck >5 min with empty request_id, refunds credits).

## Nous API proxy for OAuth-authenticated providers
Nous Portal uses OAuth (device code flow) with short-lived tokens — no static API key. Cloudflare Workers can't do OAuth.
**Fix**: run a lightweight Python HTTP proxy on the VM (systemd service on port 8901) that reads the latest `agent_key` from `~/.hermes/auth.json/providers/nous/agent_key` on each request and forwards to `inference-api.nousresearch.com/v1`. Worker calls proxy with shared secret.
Worker secrets: `NOUS_PROXY_URL`, `NOUS_PROXY_SECRET`.

## Video picker ignores conversation context for preferences
`extractVideoPrefsFromPrompt` only searched the current Telegram message for duration/resolution/ratio. If user said "3 secondes 480p" in a previous message, picker showed defaults (5s/720p).
**Fix**: pass full conversation context (all user messages from `client.context`) to picker, search both current message AND context for prefs.

## Video prompt includes technical params
When user sends "animer cette image avec un zoom en 3 secondes 480p", the stored prompt was the entire message including params.
**Fix**: `cleanPromptFromParams()` strips duration/resolution/ratio tokens before storing in draft.

## Image picker overrides conversation context
`openImageActionPicker` (Animer/Modifier/Coloriser) always showed when image sent without text, even if user already discussed intent.
**Fix**: check `client.context` — if non-empty, send image directly to agent instead of showing picker.
