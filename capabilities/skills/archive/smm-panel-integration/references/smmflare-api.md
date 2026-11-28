# SMMFlare API v2 Reference

Base URL: `https://smmflare.com/api/v2`
Method: POST (form-encoded)
Auth: `key` parameter (get from https://smmflare.com/account)

## Endpoints

### 1. List Services
```
key=<API_KEY>&action=services
```
Response: array of `{service, name, type, category, rate, min, max, refill, cancel}`

### 2. Add Order
**Type 0 (Default):**
```
key=<API_KEY>&action=add&service=<ID>&link=<URL>&quantity=<N>
```
Optional: `runs`, `interval` (for drip-feed delivery)

**Type 2 (Custom Comments):**
```
key=<API_KEY>&action=add&service=<ID>&link=<URL>&comments=<newline-separated>
```

**Type 9 (Mentions):**
```
key=<API_KEY>&action=add&service=<ID>&link=<URL>&quantity=<N>&usernames=<newline-separated>
```

**Type 10 (Package):**
```
key=<API_KEY>&action=add&service=<ID>&link=<URL>
```

**Type 100 (Subscription):**
```
key=<API_KEY>&action=add&service=<ID>&username=<USER>&min=<N>&max=<N>&delay=<MINUTES>
```
Optional: `posts`, `old_posts`, `expiry` (format d/m/Y)

**Type 102 (Web Traffic):**
```
key=<API_KEY>&action=add&service=<ID>&link=<URL>&quantity=<N>&country=<CODE>&device=<1-5>&type_of_traffic=<1-3>
```
- device: 1=Desktop, 2=Android, 3=iOS, 4=Mixed Mobile, 5=All
- type_of_traffic: 1=Google Keyword, 2=Custom Referrer, 3=Blank
- Requires `google_keyword` (if type=1) or `referring_url` (if type=2)

**Response:** `{"order": 23501}`

### 3. Order Status
Single: `key&action=status&order=<ID>`
Batch: `key&action=status&orders=<ID1,ID2,...>` (up to 100)

Response: `{charge, start_count, status, remains, currency}`
Statuses: Pending, In progress, Partial, Completed, Processing, Canceled

### 4. Balance
```
key=<API_KEY>&action=balance
```
Response: `{balance: "100.84", currency: "USD"}`

### 5. Refill
Single: `key&action=refill&order=<ID>`
Batch: `key&action=refill&orders=<ID1,ID2,...>`
Response: `{refill: "1"}` or error

### 6. Refill Status
Single: `key&action=refill_status&refill=<ID>`
Batch: `key&action=refill_status&refills=<ID1,ID2,...>`

### 7. Cancel
```
key&action=cancel&orders=<ID1,ID2,...>
```
Response: array of `{order, cancel: 1}` or `{order, cancel: {error}}`

## Service Types Summary
| Type | Description | Required Params |
|------|-------------|-----------------|
| 0 | Default | link, quantity |
| 1 | SEO | link, quantity, keywords |
| 2 | Custom Comments | link, comments |
| 3 | Mentions + Hashtags | link, quantity, usernames, hashtags |
| 4 | Mentions Custom List | link, usernames |
| 6 | Mentions Hashtag | link, quantity, hashtag |
| 7 | Mentions User Followers | link, quantity, username |
| 8 | Mentions Media Likers | link, quantity, media |
| 9 | Mentions | link, quantity, usernames |
| 10 | Package | link |
| 14 | Custom Comments Package | link, comments |
| 15 | Comment Likes | link, quantity, username |
| 17 | Poll | link, quantity, answer_number |
| 18 | Comment Replies | link, username, comments |
| 20 | Invites from Groups | link, quantity, groups |
| 100 | Subscription | username, min, max, delay |
| 102 | Web Traffic | link, quantity, country, device, type_of_traffic |

## curl Examples

```bash
# List services
curl -X POST https://smmflare.com/api/v2 -d "key=YOUR_KEY&action=services"

# Check balance
curl -X POST https://smmflare.com/api/v2 -d "key=YOUR_KEY&action=balance"

# Order 10K TikTok views
curl -X POST https://smmflare.com/api/v2 \
  -d "key=YOUR_KEY&action=add&service=SERVICE_ID&link=https://www.tiktok.com/@user/video/123&quantity=10000"

# Check order status
curl -X POST https://smmflare.com/api/v2 \
  -d "key=YOUR_KEY&action=status&order=23501"
```
