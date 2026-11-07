# Cron Delivery Patterns for Telegram

## The Doubling Problem

When a cron job has `deliver: telegram:CHAT_ID` AND the agent prompt tells it to send via curl, the message arrives TWICE:
1. Via curl (clean, agent-controlled)
2. Via cron auto-delivery (wraps the agent's final response with "Cron job response, Job ID:..." metadata)

## Solution: curl + [SILENT]

The agent sends the report via curl (full control over format), then responds with exactly `[SILENT]` to suppress the cron auto-delivery.

### Token retrieval (vault, NEVER hardcoded)

```python
import subprocess
r = subprocess.run(['vault', 'get', 'telegram/bot_token'], capture_output=True, text=True)
token = r.stdout.strip()
```

### Send function

```python
import json, urllib.request

def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({'chat_id': chat_id, 'text': text}).encode('utf-8')
    req = urllib.request.Request(url, data=payload, method='POST',
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            return result.get('ok', False)
    except urllib.error.HTTPError as e:
        return False
```

### Prompt pattern

```
Envoie sur Telegram via curl avec le token du vault (vault get telegram/bot_token).
Après l'envoi, réponds [SILENT].
```

### CRITICAL: Do NOT use placeholder text in curl template

If the prompt contains `text":"MESSAGE_ICI"`, the agent will copy it literally and send "MESSAGE_ICI" as the message. The agent must CONSTRUCT the message content and embed it in the curl command.

## 4096 char limit

Telegram rejects messages > 4096 chars with `400 Bad Request: message is too long`.

**Split strategy**: Send multiple messages — summary, content, alerts. Each sent separately via its own curl call. Never try to fit everything in one message.

## No parse_mode by default

Do NOT use `parse_mode=Markdown` or `parse_mode=HTML` unless the text is properly escaped. Markdown special chars in model names/descriptions break the formatting. Plain text is safer.

## Cron job setup for Telegram delivery

```json
{
  "name": "My Report",
  "schedule": "0 9 * * *",
  "deliver": "telegram:CHAT_ID",
  "enabled_toolsets": ["terminal", "file"]
}
```

The `deliver` field routes the agent's final response to Telegram. Combined with `[SILENT]`, only the curl-sent message reaches the user.
