# Kie.ai Common API Reference

Extracted from https://docs.kie.ai/common-api/quickstart (May 2026 session).

## Base URL

```
https://api.kie.ai
```

All endpoints require:
```
Authorization: Bearer <token>
Content-Type: application/json
```

## Check Account Credits

```bash
GET /api/v1/chat/credit
```

**Response:**
```json
{"code":200,"msg":"success","data":879.7}
```

- `data` is a float (remaining credits)
- No parameters required
- Immediate response

## Get Download URL for Generated Files

```bash
POST /api/v1/common/download-url
```

**Body:**
```json
{"url": "https://generated-file-url-from-kie.ai/..."}
```

**Response:**
```json
{"code":200,"msg":"success","data":"https://tempfile.1f6cxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxbd98"}
```

- Link valid for **20 minutes only**
- Only works with kie.ai generated URLs (external URLs → 422)
- Use immediately after obtaining

## Webhook Security Verification

```bash
POST /api/v1/common/webhook-verification
```

See docs at https://docs.kie.ai/common-api/webhook-verification for signature validation.

## Async Task Model

All generation tasks are async. A 200 OK on create only means the task was **created**, not completed.

To get final results:
1. Provide `callBackUrl` in create request (preferred for production)
2. Poll query endpoint with `taskId`

## Rate Limits

- Up to 20 new generation requests per 10 seconds
- 100+ concurrent running tasks typical
- Per-account limits
- Exceeding → HTTP 429, requests not queued

## Data Retention

- Generated media files: **14 days**, then auto-deleted
- Log records (text/metadata): **2 months**, then auto-deleted
- Download and cache results locally if long-term access needed

## Support

- Discord / Telegram (private 1-on-1 channels, fastest)
- Email: support@kie.ai (slower)
- Support hours: UTC 21:00 – UTC 17:00 (next day)
