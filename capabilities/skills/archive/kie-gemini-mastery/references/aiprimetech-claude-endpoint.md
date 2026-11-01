# AIPrimeTech Claude Endpoint

## Endpoint

```
POST https://aiprimetech.io/v1/messages
x-api-key: <AIPRI_CLAUDE_KEY>
Content-Type: application/json
anthropic-version: 2023-06-01
```

**Critical:** AIPrimeTech Claude uses `x-api-key` header (NOT `Authorization: Bearer`). Both work on the same endpoint according to tests (2026-06-11), but `x-api-key` is the canonical Anthropic format.

## Model Names

| Model | Body `model` field |
|-------|-------------------|
| Claude Opus 4.8 | `claude-opus-4-8` |
| Claude Opus 4.7 | `claude-opus-4-7` |
| Claude Opus 4.6 | `claude-opus-4-6` |

## Request Format (Standard Anthropic Messages)

```json
{
    "model": "claude-opus-4-8",
    "messages": [{"role": "user", "content": "Your prompt"}],
    "max_tokens": 16000
}
```

**Important:** Omit `thinking`/`thinkingFlag`/`reasoning` parameters. AIPrimeTech proxies do not return thinking blocks regardless of these flags — sending them wastes tokens on parameter processing without benefit.

## Key Extraction Workflow

AIPrimeTech masks API keys in the UI (`«secret:vault»`). To get the full key:

1. Navigate to `https://aiprimetech.io/keys` in Camoufox (authenticated via localStorage JWT)
2. Click "Use Key" on the Claude row (not the Codex or Image rows)
3. Switch to the "OpenCode" tab in the modal
4. Extract the `apiKey` value from the JSON code block: `"apiKey": "sk-<full_key>"`
5. Save to file (`/tmp/aipri-claude-key.txt`)

**Pitfall:** The auth token in localStorage expires. If `/api/v1/keys` returns empty or the dashboard redirects to `/login`, re-login first (email: earndeel@gmail.com, credentials in vault `aiprimetech/credentials`).

## Observed Behavior vs Kie.ai Claude (2026-06-11)

Same prompt, same model (`claude-opus-4-8`), different providers:

| Metric | Kie.ai | AIPrimeTech |
|--------|--------|-------------|
| Endpoint | `api.kie.ai/claude/v1/messages` | `aiprimetech.io/v1/messages` |
| Auth | Bearer | x-api-key |
| Output chars | 22,196 | 16,117 |
| Output tokens | 7,731 | 5,922 |
| Cache hit | 0 | 0 |

Kie.ai produced 38% more output for the identical prompt. Likely different system prompts or generation parameters on the proxy side.

## HTML Truncation at max_tokens

When generating long HTML documents, Claude may truncate mid-tag when `max_tokens` is hit. The output is valid JSON but the HTML content is incomplete — missing closing `</body></html>` tags, broken CSS blocks, or truncated inline styles.

**Symptoms:** Browser renders content but layout is broken or styles are missing. View-source shows the HTML ends abruptly.

**Mitigation:**
1. Use `"max_tokens": 16000` (the default cap) — do NOT set lower
2. Prompt for concise output: "Return ONLY the complete HTML document. Be concise."
3. Verify completeness: check if the response ends with `</html>` before serving
4. If truncated: re-request with a shorter prompt scope or split into components

## AIPrimeTech Keys Available

| Service | Key prefix | Notes |
|---------|-----------|-------|
| Claude Max | `sk-778...` | Claude 4.8, 4.7, 4.6 |
| Image-2 | `sk-aba...` | GPT-Image-2, often 503 |
| Codex | `sk-e03...` | GPT-5.5 via Responses API |
