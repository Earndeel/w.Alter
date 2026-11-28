---
name: cloudflare-worker-custom-domain
description: Point a custom domain to a Cloudflare Worker via DNS + Worker Route
category: cloud
tags: [cloudflare, worker, dns, route, custom-domain]
---

# Cloudflare Worker Custom Domain Setup

Point a custom domain (on the same Cloudflare zone) to a Worker.

## When to use
- Migrating from CF Tunnel to Worker for a subdomain
- Setting up a new custom domain for a Worker
- Centralizing routing through the Worker instead of VM

## Prerequisites
- Worker already deployed
- Custom domain on same Cloudflare zone
- Cloudflare Global API Key or scoped token with DNS + Workers permissions

## Steps

### 1. Update DNS Record
Change the CNAME from Tunnel (or whatever) to the workers.dev URL:

```python
import requests

headers = {
    'X-Auth-Key': 'CF_GLOBAL_KEY',
    'X-Auth-Email': 'EMAIL',
    'Content-Type': 'application/json',
}

# Get current DNS record
r = requests.get(f'https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records', headers=headers)
for rec in r.json()['result']:
    if rec['name'] == 'api.example.com':
        record_id = rec['id']

# Update to CNAME → workers.dev
requests.put(
    f'https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records/{record_id}',
    headers=headers,
    json={
        "type": "CNAME",
        "name": "api.example.com",
        "content": "my-worker.account.workers.dev",
        "proxied": True,
        "ttl": 1
    }
)
```

### 2. Create Worker Route
Map the hostname pattern to the Worker script:

```python
requests.post(
    f'https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/workers/routes',
    headers=headers,
    json={
        "pattern": "api.example.com/*",
        "script": "my-worker-name"
    }
)
```

If route already exists (code 10020), it's already configured.

### 3. Update External Webhooks
Any third-party service (Stripe, PiAPI, etc.) pointing to workers.dev should be updated to the custom domain for consistency.

### 4. Verify
```python
r = requests.get("https://api.example.com/health")
assert r.status_code == 200
```

## Pitfalls
- Worker Route must exist alongside DNS record (both required)
- If route already exists, API returns error 10020 — safe to ignore
- DNS propagation is instant when proxied (orange cloud)
- Keep the old Tunnel running for other services if needed, just remove this one subdomain
- Stripe webhook URLs must be updated separately via Stripe API
