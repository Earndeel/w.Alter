# Tinder API Reference

## Authentication
Token stored in vault: `vault get tinder/api_token`
Header: `X-Auth-Token: <token>`

## Working Endpoints (as of 2026-05)

### GET /updates (primary data source)
Returns all matches with full person data + messages.
```bash
curl -s "https://api.gotinder.com/updates" \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"nudge":false,"message_page":0,"page_token":null}' \
  -o /tmp/tinder_updates.json
```
**Pitfall:** Response contains control characters — always parse with `json.loads(raw, strict=False)`.

### Response structure
```json
{
  "matches": [
    {
      "_id": "match_id",
      "person": {
        "_id": "person_id",
        "name": "Display Name",
        "birth_date": "1993-05-25T17:42:12.979Z",
        "bio": "...",
        "gender": 1,
        "photos": [{"url": "https://images-ssl.gotinder.com/..."}],
        "jobs": [],
        "schools": []
      },
      "messages": [
        {"from": "person_id", "message": "text", "sent": "..."}
      ],
      "distance_mi": 5,
      "last_activity_date": "2026-05-11T12:27:00.844Z"
    }
  ]
}
```

### Photo URLs
Format: `https://images-ssl.gotinder.com/{person_id}/original_{uuid}.jpg`
These are ephemeral CDN links — download immediately with `curl -s -o /tmp/tinder_photo_N.jpg "$URL"`.

### Broken endpoints (401 as of 2026-05)
- `GET /v2/matches` → 401
- `GET /v2/profile` → 200 but empty data
- `GET /v2/recs/core` → 401

## Photo OSINT Workflow
1. Download all photos from `person.photos[].url`
2. Analyze each with `vision_analyze`:
   - Physical appearance (hair color natural vs dyed, age estimate, skin tone)
   - Location landmarks (architecture, vegetation, signs, skyline)
   - Clothing brands/jewelry (luxury indicators)
   - Background setting (hotel, apartment, resort, city)
   - Any text, logos, or brand names
3. Cross-reference location clues across photos to build travel/residence profile
4. Natural hair color (from travel/vacation photos) vs current (from recent selfies) reveals style changes
