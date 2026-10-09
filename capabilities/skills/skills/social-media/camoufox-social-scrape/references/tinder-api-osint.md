# Tinder API for OSINT

## Authentication
Token from vault: `vault get tinder/api_token`
Header: `X-Auth-Token: <token>`

## Endpoints

### GET /updates (primary — works with expired auth)
```bash
curl -s "https://api.gotinder.com/updates" \
  -H "X-Auth-Token: <token>" \
  -H "Content-Type: application/json" \
  -d '{"nudge":false,"message_page":0,"page_token":null}' \
  -o /tmp/tinder_updates.json
```
Parse with `json.loads(raw, strict=False)` — responses contain control characters.

### v2 endpoints (require fresh auth, often 401)
- `GET /v2/profile` — own profile
- `GET /v2/matches?count=100` — matches (may 401)
- `GET /v2/recs/core` — recommendations (401)

## Data available per match
```json
{
  "person": {
    "_id": "69dd1c0debf1d75645fb3b28",
    "name": "Elissa",
    "bio": "...",
    "birth_date": "1993-05-25T17:42:12.979Z",
    "gender": 1,
    "jobs": [],
    "schools": [],
    "photos": [
      {"url": "https://images-ssl.gotinder.com/{id}/original_{uuid}.jpg"}
    ]
  },
  "messages": [
    {"from": "{person_id}", "message": "text"},
    {"from": "{your_id}", "message": "text"}
  ],
  "distance_mi": null,
  "last_activity_date": "2026-05-11T12:27:00.844Z"
}
```

## Photo URLs
Pattern: `https://images-ssl.gotinder.com/{person_id}/original_{uuid}.jpg`
Download: `curl -s -o /tmp/tinder_photo_N.jpg "<url>"`
Photos are public URLs — no auth needed to download.

## OSINT from Tinder data
- **birth_date** → exact age calculation
- **name** → may be first name only, nickname, or second name (not necessarily legal name)
- **messages** → reveals language, location (neighborhood), profession, travel history
- **photos** → reverse image search, location clues (landmarks, architecture, vegetation)
- **jobs/schools** → often empty but when present, strong identifiers
- **last_activity_date** → recency of use
