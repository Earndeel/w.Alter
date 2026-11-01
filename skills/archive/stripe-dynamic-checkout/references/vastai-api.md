# Vast.ai API Reference

## Authentication
- **Session cookie**: `auth_tkt` (from Google OAuth login in browser)
- **API key**: Bearer token in `Authorization` header
- **Key file**: `~/.config/vastai/vast_api_key`

## Key Endpoints

### User
```
GET /api/v0/users/current/          # Current user info (balance, can_pay, etc.)
GET /api/v0/users/root/             # Root user info
```

### API Keys (CRITICAL — non-obvious path!)
```
GET  /api/v0/auth/apikeys/          # List API keys (key field is null for existing keys)
POST /api/v0/auth/apikeys/          # Create API key — returns full key ONCE
                                     # Body: {"name": "key-name"}
                                     # Response: {"success": true, "id": ..., "key": "full-hex-key"}
DELETE /api/v0/auth/apikeys/{id}/   # Delete API key
```

**⚠️ WRONG paths that return 404:**
- `/api/v0/apikeys/` → 404
- `/api/v0/users/current/apikeys/` → 404
- `/api/v0/api-keys/` → 404

### Billing
```
GET /api/v0/users/current/payment-methods/   # List saved cards (returns [] if none)
```

### SSH Keys
```
GET /api/v0/ssh/                    # List SSH keys
```

### Instances
```
GET /api/v0/instances/              # List instances
```

### CLI
```
vastai show user                    # User info
vastai search offers 'gpu_name=RTX_4090'  # Search GPU offers
vastai launch ...                   # Launch instance
```

## API Key Creation via Browser
The frontend truncates the key in the UI (`745600ea...6db2`). To get the full key:
```python
result = page.evaluate("""
    async () => {
        const resp = await fetch('/api/v0/auth/apikeys/', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: 'walter-auto'})
        });
        return await resp.json();
    }
""")
full_key = result['key']  # Full hex key
```

## Account Details
- User ID: 347995
- Email: lucas.jouvencon@gmail.com (Google OAuth)
- Balance: $0.00 (needs credit card)
