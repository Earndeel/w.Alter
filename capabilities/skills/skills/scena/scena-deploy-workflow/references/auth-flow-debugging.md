# Scena Auth Flow — Debugging Reference

## Google OAuth Flow

```
Browser → GET /api/auth/google (302 → Google)
Google → GET /api/auth/google/callback?code=...&state=...
Worker verifies state in `verification` table (CSRF)
Worker exchanges code for tokens via oauth2.googleapis.com/token
Worker fetches userinfo from googleapis.com
Worker finds/creates user in D1 `users` table
Worker sets cookie: scena_session=...; Domain=.walter-ai.cloud; HttpOnly; Secure; SameSite=Lax
Worker redirects → https://scena.walter-ai.cloud/?auth=success
```

## Session Check Endpoints

| Endpoint | Used by | Notes |
|---|---|---|
| `/api/auth/get-session` | Portal, login page | Returns `{ user }` or `null` |
| `/api/auth/session` | **DEPRECATED** — old portal code | May not exist; causes silent failures |

When portal doesn't restore session on load, check if it's calling the wrong endpoint.

## Cookie Domain

Cookie is set on `Domain=.walter-ai.cloud` (with leading dot), so it works across:
- `scena.walter-ai.cloud` (portal)
- `admin-scena.walter-ai.cloud` (admin)
- `api.walter-ai.cloud` (API)

## Common Failures

| Symptom | Cause | Fix |
|---|---|---|
| Google button returns 404 | Worker not deployed after code change | `wrangler deploy --name=scena-api` |
| Google redirects but session not restored | Portal calls `/api/auth/session` instead of `/api/auth/get-session` | Patch portal JS |
| Login works but dashboard doesn't load | CORS or cookie not sent | Check `credentials:'include'` on fetch |
| `curl -sI` shows 404 on auth endpoint | HEAD request not handled | Use `curl -s` (GET) instead |
