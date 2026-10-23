---
name: telegram-bot-pool-auto-provisioning
description: Pre-create Telegram bots via @BotFather, store tokens in a pool DB, and auto-assign to clients on signup.
version: 1.0
---

# Telegram Bot Pool — Auto-Provisioning for Multi-Tenant SaaS

## Problem
Telegram's BotFather has no API for creating bots programmatically. But you need to assign a unique bot to each client automatically on signup.

## Solution
Pre-create a pool of bots manually, store tokens in a DB, and auto-assign on client signup.

## Steps

### 1. Create bots manually via @BotFather
```
/newbot → "Scena Slot 1" → "scena_slot1_bot" → get token
/newbot → "Scena Slot 2" → "scena_slot2_bot" → get token
...
```

### 2. Pool DB schema
```sql
CREATE TABLE bot_pool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT UNIQUE NOT NULL,
    bot_username TEXT DEFAULT '',
    slot_name TEXT DEFAULT '',
    status TEXT DEFAULT 'available',  -- available, assigned, disabled
    assigned_to TEXT DEFAULT '',
    assigned_at REAL,
    created_at REAL DEFAULT (unixepoch())
);
```

### 3. Auto-assign on signup
```python
def assign_bot(client_id, client_name=""):
    """Assign next available bot to a client."""
    conn = get_db()
    bot = conn.execute(
        "SELECT * FROM bot_pool WHERE status = 'available' ORDER BY id LIMIT 1"
    ).fetchone()
    
    if not bot:
        return {"ok": False, "error": "No available bots"}
    
    conn.execute("""
        UPDATE bot_pool SET status = 'assigned', assigned_to = ?, assigned_at = unixepoch()
        WHERE id = ?
    """, (client_id, bot["id"]))
    conn.commit()
    conn.close()
    
    return {"ok": True, "token": bot["token"], "bot_username": bot["bot_username"]}
```

### 4. Validate token before adding to pool
```python
def validate_token(token):
    url = f"https://api.telegram.org/bot{token}/getMe"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    if data.get("ok"):
        return data["result"]  # {id, username, first_name, ...}
    return None
```

### 5. Send welcome message
```python
def send_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(url, data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=10)
```

### 6. Release bot when client is deleted
```python
def release_bot(client_id):
    conn.execute("""
        UPDATE bot_pool SET status = 'available', assigned_to = ''
        WHERE assigned_to = ?
    """, (client_id,))
    conn.commit()
```

## Full Auto-Provisioning Flow
```python
def auto_provision(client_id, client_name, email):
    # 1. Assign bot
    bot = assign_bot(client_id, client_name)
    if not bot["ok"]:
        return bot
    
    # 2. Create client environment (DB, dashboard, config)
    config = create_client(name=client_name, email=email, 
                          telegram_token=bot["token"])
    
    # 3. Return bot link to client
    return {
        "ok": True,
        "bot_link": f"https://t.me/{bot['bot_username']}",
        "bot_username": bot["bot_username"]
    }
```

## Key Learnings
- BotFather has no API — manual creation is the only way
- Validate tokens before adding to pool (catches typos early)
- Store bot_username for generating t.me links
- Release bots back to pool when clients are deleted/suspended
- Monitor pool size — create more bots when running low
- Each bot gets its own process polling for updates
