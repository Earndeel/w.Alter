# Contact Lookup Patterns

## SQL Queries for Kardex

### Search by any identifier
```sql
-- Comprehensive search across all fields
SELECT 
    c.id,
    c.canonical_name,
    c.aliases,
    c.handles,
    c.phone_numbers,
    c.emails,
    c.relationship_type,
    c.relationship_status,
    c.personality_profile,
    c.total_messages
FROM kardex.contacts c
WHERE 
    c.canonical_name ILIKE '%search_term%'
    OR 'search_term' = ANY(c.aliases)
    OR c.handles::text ILIKE '%search_term%'
    OR c.phone_numbers @> ARRAY['search_term']
    OR c.emails @> ARRAY['search_term%'];

-- Search across channels (Beeper handles, Instagram, etc.)
SELECT 
    c.id,
    c.canonical_name,
    ch.platform,
    ch.platform_handle,
    ch.platform_id
FROM kardex.contacts c
JOIN kardex.channels ch ON c.id = ch.contact_id
WHERE 
    ch.platform_handle ILIKE '%search_term%'
    OR ch.platform_id ILIKE '%search_term%';

-- Search messages for mentions
SELECT DISTINCT
    c.id,
    c.canonical_name,
    COUNT(m.id) as mention_count
FROM kardex.contacts c
JOIN kardex.messages m ON c.id = m.contact_id
WHERE 
    m.text ILIKE '%search_term%'
    OR m.text ILIKE '%@search_term%'
GROUP BY c.id, c.canonical_name
ORDER BY mention_count DESC;
```

### Search by relationship attributes
```sql
-- Find contacts by relationship type
SELECT * FROM kardex.contacts 
WHERE relationship_type = 'romantic'
ORDER BY last_contact_date DESC;

-- Find contacts by location
SELECT * FROM kardex.contacts 
WHERE location_current ILIKE '%bangkok%'
   OR location_home ILIKE '%bangkok%';

-- Find contacts by age range
SELECT * FROM kardex.contacts 
WHERE age_approx::int BETWEEN 25 AND 35;
```

## Beeper API Queries

### List all chats with message counts
```bash
# Get all single chats with stats
python3 -c "
import json, subprocess
TOKEN = subprocess.check_output('vault get beeper/token', shell=True).decode().strip()
API = 'http://100.127.150.1:23373'
chats = json.loads(subprocess.check_output(
    f'curl -s \"{API}/v1/chats\" -H \"Authorization: Bearer {TOKEN}\"',
    shell=True
))['items']
for c in chats:
    if c['type'] == 'single':
        print(f\"{c['title']:30} | {c['id']:40} | {c.get('unreadCount', 0)} unread\")
"
```

### Search chats by handle/name
```bash
# Search for specific contact
python3 -c "
import json, subprocess
TOKEN = subprocess.check_output('vault get beeper/token', shell=True).decode().strip()
API = 'http://100.127.150.1:23373'
chats = json.loads(subprocess.check_output(
    f'curl -s \"{API}/v1/chats\" -H \"Authorization: Bearer {TOKEN}\"',
    shell=True
))['items']
search = 'lcomte63'.lower()
for c in chats:
    if search in c.get('title', '').lower():
        print(f\"Found: {c['title']} | {c['id']}\")
"
```

## Session Search Patterns

### Discovery search
```python
# Search across all sessions
session_search(query="lcomte63", limit=10)

# Try variations
session_search(query="lcomte63 OR lcomte OR comte63", limit=10)
session_search(query="Lucas comte", limit=10)
```

### Platform-specific search
```python
# If you know the platform
session_search(query="instagram lcomte63", limit=5)
session_search(query="bumble lcomte63", limit=5)
session_search(query="whatsapp lcomte63", limit=5)
```

## Common Handle Patterns

| Platform | Handle Format | Example |
|----------|--------------|---------|
| Instagram | @username | @lcomte63 |
| Telegram | @username or t.me/username | @lcomte63 |
| WhatsApp | phone number | +33612345678 |
| Bumble | display name (not handle) | "Lucas" |
| Beeper | platform_handle or display name | varies |

## Troubleshooting

### PG Connection Failed
```bash
# 1. Check if container is running
docker ps | grep hindsight-pg

# 2. Get current IP
docker inspect hindsight-pg | grep IPAddress

# 3. Update scripts if IP changed
sed -i 's/DB_HOST = ".*"/DB_HOST = "172.17.0.X"/' /root/.hermes/services/kardex/scripts/*.py

# 4. Test connection
psql -h 172.17.0.X -U postgres -d hermes -c "SELECT 1;"
```

### Beeper API Unreachable
```bash
# 1. Check Beeper service
curl -s http://100.127.150.1:23373/v1/chats -H "Authorization: Bearer $(vault get beeper/token)"

# 2. Check vault has token
vault get beeper/token

# 3. Check network (Tailscale)
ping 100.127.150.1
```

### Contact Exists But Not Found
- Check if handle has special characters (accents, underscores)
- Try case-insensitive search
- Check if contact is in a different schema (public vs kardex)
- Verify contact was synced (check `kardex.channels` table)
