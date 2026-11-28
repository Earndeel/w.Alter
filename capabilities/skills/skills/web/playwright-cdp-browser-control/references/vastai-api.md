# Vast.ai API Reference

## Registration

**Endpoint**: `POST https://cloud.vast.ai/api/v0/users/`

**Required fields**:
```json
{
  "email": "user@example.com",
  "username": "username",
  "password": "...",
  "captcha": "<reCAPTCHA token from grecaptcha.execute()>",
  "ssh_key": null,
  "host_only": false,
  "gclid": "",
  "rdt_cid": "",
  "twclid": "",
  "li_fat_id": "",
  "fbclid": "",
  "referrer": "Direct",
  "utm_source": "",
  "utm_medium": "",
  "utm_campaign": "",
  "utm_term": "",
  "utm_content": "",
  "landing_page": "",
  "external": 0
}
```

**Responses**:
- `200` / `201` — success, account created
- `400` `{"error":"missing_auth_value"}` — captcha field missing
- `400` `{"error":"bad_request","msg":"recaptcha_token: Extra inputs are not permitted"}` — wrong field name (use `captcha`, not `recaptcha_token`)
- `409` — email or username already exists
- `403` — auth error (not logged in)

**reCAPTCHA sitekey**: `6LfjEokUAAAAAEtA93AOFkZGKl-QzM9c5iqa320v` (invisible v2)

**reCAPTCHA action**: `'register'`

## Login

No dedicated `/login/` route — it's a React SPA with a modal login dialog.

The `POST` endpoint for login exists but the exact path is unclear (not `/api/v0/users/login/` which returns 404). Login is handled client-side.

**Workaround**: Use browser automation to fill the login modal, or use API key auth for CLI.

## CLI

```bash
pip install vastai
vastai --api-key YOUR_KEY search offers 'gpu_name=RTX_4090'
```

Auth via API key only (no username/password login in CLI).

## Console vs Cloud

- `cloud.vast.ai` — main UI, registration, GPU marketplace
- `console.vast.ai` — same SPA, API calls go here
- API calls from browser use `cloud.vast.ai/api/v0/` prefix

## Account Info

```bash
# Check current user
curl -s "https://cloud.vast.ai/api/v0/users/current/" -H "Authorization: Bearer API_KEY"

# List API keys
curl -s "https://cloud.vast.ai/api/v0/apikeys/" -H "Authorization: Bearer API_KEY"
```
