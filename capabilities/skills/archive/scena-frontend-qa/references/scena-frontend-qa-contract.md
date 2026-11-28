# Scena Frontend QA Contract

## Surface map

| Surface | Local source | Production path | API scope |
|---|---|---|---|
| Client portal | `pages/portal/dashboard.html` | `scena.walter-ai.cloud/dashboard` | authenticated tenant client |
| Admin control plane | `pages/admin/index.html` | `admin-scena.walter-ai.cloud/` | admin bearer session |
| Operator Studio | `pages/admin/operator.html` | `admin-scena.walter-ai.cloud/operator` | operator workflow APIs |

Do not treat the admin control plane and Operator Studio as the same UI. The bot status issue belongs to the client portal and API tenant route; the requested admin redesign belongs to `pages/admin/index.html`.

## Telegram route contract

The safe tenant response is configuration metadata, not a secret:

```json
{
  "connected": true,
  "telegram_bot_configured": true,
  "bot_username": "scena_bot",
  "bot_name": "@scena_bot",
  "telegram_chat_id": ""
}
```

Required behavior:

- `GET /api/client/bot` resolves the current client and returns the safe status object.
- `POST /api/client/bot` accepts `{ "bot_token": "..." }`; a legacy `telegram_bot_token` input may be accepted during migration.
- `DELETE /api/client/bot` clears bot token, username, and chat ID only on the current client row.
- No route returns `telegram_bot_token` or any raw credential.
- A configured token is not proof of live Telegram reachability unless the route explicitly performs and reports a provider probe.

## Regression checks

The Worker harness should cover:

1. POST updates the client row without writing to shared bot state.
2. GET returns `connected`/`telegram_bot_configured` and the bot name while omitting the secret.
3. DELETE clears the current client’s bot fields and returns a disconnected state.
4. Authenticated client resolution remains tenant-scoped.

The portal browser fixture should capture the request body from the save action and assert that it is `{ bot_token: value }`, not `{ telegram_bot_token: value }`.

## Admin DOM invariants

- Overview and the Clients tab must not share an ID. Use `overview-clients-grid` and `clients-grid`.
- If `switchTab()` queries `[data-tab]`, each nav button needs the matching attribute.
- Startup loaders must tolerate absent panels. Removed panels should be removed from startup loading or their render target should be checked before writing.
- Client Brain should exercise the existing brain API and expose `Agent.md`, `Basic User.md`, system overrides, and generated memory content.
- Knowledge Hub template buttons must call a real workflow action or be labeled as preview-only.

## Browser fixture recipe

Use a local server for the relevant static directory. Route API requests on the browser context so every page created in the same run receives the same fixtures. Use separate pages or contexts for desktop and 390px mobile; wait for asynchronous startup loads before capture.

Record:

- page errors;
- failed requests;
- active tab ID;
- document width versus viewport width;
- visible card and modal dimensions;
- captured bot save payload.

Expected browser assertions:

- authenticated startup hides the login overlay;
- the returned bot name is visible;
- admin tab clicks activate the requested tab;
- Client Brain opens and closes;
- no horizontal overflow at 390px;
- no page errors or failed API requests.

## Visual review checklist

Inspect at least:

- admin overview desktop;
- admin overview at 390px;
- Clients tab with a client card;
- Client Brain modal;
- Knowledge Hub desktop.

Look for clipped nav labels, duplicate/hidden client cards, missing mobile stats, unreadable contrast, modal overflow, zero-height cards, and empty states that lack an explicit message. A tall Workflow Runs card is acceptable when `Aucun run` is visible and its loader succeeded.
