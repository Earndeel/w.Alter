# Vast.ai API Reference

## Registration
```
POST https://cloud.vast.ai/api/v0/users/
Content-Type: application/json

{
  "email": "user@email.com",
  "username": "username",
  "password": "password",
  "ssh_key": null,
  "captcha": "RECAPTCHA_TOKEN",
  "host_only": false,
  "gclid": "",
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

**Key details:**
- Field is `captcha` (NOT `recaptcha_token`)
- reCAPTCHA sitekey: `6LfjEokUAAAAAEtA93AOFkZGKl-QzM9c5iqa320v`
- 409 = account already exists (email or username taken)
- 400 = missing captcha or validation error

## Login
No `/login/` URL — login is via modal on main page (`cloud.vast.ai`).
Login uses Google OAuth ("Continue with Google") or email/password via modal.
After login, API key available at `/api/v0/apikeys/`.

## Get API Keys
```
GET https://cloud.vast.ai/api/v0/apikeys/
Cookie: <session cookies from login>
```

## Create API Key
```
POST https://cloud.vast.ai/api/v0/apikeys/
Content-Type: application/json

{"name": "walter-auto"}
```

## CLI
```bash
pip install vastai
vastai set api-key <KEY>
vastai search offers 'gpu_name=RTX_4090 num_gpu=1'
vastai create instance <offer_id>
```

## Known Account
- Email: lucas.jouvencon@gmail.com (NOT jouvenson)
- Registered via Google OAuth
- Password unknown — use Google OAuth or password reset to access
