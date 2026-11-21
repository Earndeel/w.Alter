# Scena Telegram client-status reference

## Symptom

The authenticated Scena dashboard shows `Non connecté` while the same bot answers test messages in Telegram.

## Root-cause pattern

The portal can falsely report a disconnected bot when:

1. The browser calls `GET /api/client/bot` but the Worker implements only `POST /api/client/bot`; the browser catches the failed request and leaves the initial label unchanged.
2. The browser sends `{telegram_bot_token: token}` while the Worker reads `body.bot_token`; the connect request returns `400 Token required`.
3. Telegram tests use the Worker-level `env.TELEGRAM_BOT_TOKEN` or a legacy webhook mapping, while the dashboard checks the authenticated tenant's `clients.telegram_bot_token`.
4. The bot is stored under a different client matricule, duplicate email row, or Telegram-created user.

## Safe probe sequence

1. `search_files` for `api/client/bot`, `bot_token`, `telegram_bot_token`, and `webhook/telegram` in both portal and Worker source.
2. Read the call sites and route handlers; compare method, path, body key, and response fields.
3. Probe the live API with a real authenticated session. Unauthenticated `401` only proves the auth guard, not whether the route exists behind it.
4. Query D1 read-only with the redacted projection in the parent skill. Return only IDs, matricule, username, status, chat ID, and a configured boolean.
5. Check webhook routing by matricule and, if needed, Telegram `getWebhookInfo`; never print the token.

## Regression cases

- Configured client + `GET /api/client/bot` returns a safe payload and the dashboard renders the username.
- Empty client token returns `{configured:false}` and the dashboard renders the disconnected state.
- `POST /api/client/bot` accepts `{bot_token}` and rejects missing/invalid tokens without persisting them.
- The browser never receives `telegram_bot_token`.
- A global Worker bot token does not make an unrelated tenant appear configured.
- A webhook update writes `telegram_chat_id` only on the client selected by its matricule route.

## Reporting language

If the individual D1 row was not inspected, say: “Le contrat du code explique le faux statut ; l’état exact de votre ligne client reste à confirmer.” Do not claim that the user's bot is globally disconnected merely because the dashboard label is stale.
