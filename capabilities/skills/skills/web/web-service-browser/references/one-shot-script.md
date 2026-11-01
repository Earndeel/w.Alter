# web-service-browser — The full one-shot script for a single service.

Moved verbatim from SKILL.md on 2026-11-01.

## One-Shot Script (single service)

Save to `/tmp/ws-browser.py` and run via `docker exec webtop python3 /tmp/ws-browser.py`.

```python
#!/usr/bin/env python3
"""Web Service Browser — one-shot cookie extract + inject + navigate."""
import http.client, json, time, hashlib, subprocess, sys
from Crypto.Cipher import AES

# --- CONFIG ---
SERVICE = sys.argv[1] if len(sys.argv) > 1 else "gemini"
VAULT_KEY_CACHE = "/tmp/.brave_key_derived"

SERVICES = {
    "gemini":  {"url": "https://gemini.google.com/app",    "cookie_domains": ["google", "gemini"]},
    "suno":    {"url": "https://suno.com",                 "cookie_domains": ["suno"]},
    "grok":    {"url": "https://grok.com",                  "cookie_domains": ["grok", "x.ai"]},
    "chatgpt": {"url": "https://chatgpt.com",              "cookie_domains": ["openai", "chatgpt"]},
    "claude":  {"url": "https://claude.ai",                 "cookie_domains": ["claude", "anthropic"]},
    "youtube": {"url": "https://youtube.com",               "cookie_domains": ["google", "youtube"]},
    "twitter": {"url": "https://x.com",                     "cookie_domains": ["x.com", "twitter"]},
    "facebook":{"url": "https://facebook.com",              "cookie_domains": ["facebook"]},
    "instagram":{"url": "https://instagram.com",            "cookie_domains": ["instagram"]},
    "instagram":{"url": "https://instagram.com",            "cookie_domains": ["instagram"]},
    "instagram":{"url": "https://instagram.com",            "cookie_domains": ["instagram"]},
    "hailuo":   {"url": "https://hailuoai.video/subscribe",  "cookie_domains": ["hailuoai"]},
    "bumble":   {"url": "https://bumble.com/app",           "cookie_domains": ["bumble"]},
}

if SERVICE not in SERVICES:
    print(f"Unknown service: {SERVICE}. Available: {', '.join(SERVICES.keys())}")
    sys.exit(1)

svc = SERVICES[SERVICE]
session_key = f"{SERVICE}-{int(time.time())}"

# --- STEP 1: Get keychain key ---
def get_key():
    r = subprocess.run(["vault", "get", "macos/brave_keychain_key"], capture_output=True, text=True)
    return r.stdout.strip().encode()

# --- STEP 2: Extract + decrypt cookies from Mac ---
def extract_cookies():
    keychain_value = get_key()
    derived_key = hashlib.pbkdf2_hmac('sha1', keychain_value, b'saltysalt', 1003, dklen=16)
    
    # Copy fresh Cookies DB
    subprocess.run(["ssh", "lucasjouvencon@100.127.150.1",
        "cp ~/Library/Application\\ Support/BraveSoftware/Brave-Browser/Default/Cookies /tmp/brave-cookies-latest.db"],
        check=True, capture_output=True, timeout=10)
    
    # Build SQL WHERE clause
    where = " OR ".join(f"host_key LIKE '%{d}%'" for d in svc["cookie_domains"])
    result = subprocess.run(["ssh", "lucasjouvencon@100.127.150.1",
        f"sqlite3 /tmp/brave-cookies-latest.db \"SELECT host_key, name, hex(encrypted_value), path, is_secure, is_httponly, expires_utc FROM cookies WHERE {where}\""],
        capture_output=True, text=True, timeout=15)
    
    def decrypt(hex_str):
        enc = bytes.fromhex(hex_str)
        if enc[:3] == b'v10': enc = enc[3:]
        elif enc[:4] == b'v11': enc = enc[4:]
        iv, data = enc[:16], enc[16:]
        cipher = AES.new(derived_key, AES.MODE_CBC, iv)
        dec = cipher.decrypt(data)
        pad = dec[-1]
        if 1 <= pad <= 16 and all(b == pad for b in dec[-pad:]): dec = dec[:-pad]
        clean = dec[16:] if len(dec) > 16 else dec
        return bytes(b for b in clean if 32 <= b <= 126).decode('ascii', errors='replace')
    
    cookies = []
    for line in result.stdout.strip().split('\n'):
        parts = line.split('|')
        if len(parts) < 7: continue
        host, name, enc_hex, path, secure, httponly, expires = parts
        val = decrypt(enc_hex)
        if not val or len(val) < 2: continue
        c = {"name": name, "value": val, "domain": host, "path": path,
             "secure": secure == '1', "httpOnly": httponly == '1'}
        exp = int(expires) if expires else 0
        if exp > 0: c["expires"] = int((exp / 1000000) - 11644473600)
        cookies.append(c)
    
    # Filter analytics
    EXCLUDE = ('_ga', '_gcl', '_dd', 'ajs_', 'IR_', '_gat', '_gid')
    auth = [c for c in cookies if not any(c['name'].startswith(p) for p in EXCLUDE)]
    return auth

# --- MULTI-SERVICE MODE ---
# When opening multiple services: extract once, merge ALL cookies, inject in ONE call, then create tabs in parallel.
# Multiple /sessions/walter/cookies calls with same userId OVERWRITE previous cookies.

# --- STEP 3: Ensure Camoufox is running ---
def ensure_camoufox():
    conn = http.client.HTTPConnection("localhost", 9378)
    try:
        conn.request("GET", "/health")
        resp = conn.getresponse()
        if resp.status == 200:
            return True
    except: pass
    return False

# --- STEP 4: Inject + navigate ---
def inject_and_navigate(cookies):
    conn = http.client.HTTPConnection("localhost", 9378)
    
    # Inject cookies
    body = json.dumps({"cookies": cookies})
    conn.request("POST", "/sessions/walter/cookies", body, {"Content-Type": "application/json"})
    resp = conn.getresponse()
    result = json.loads(resp.read().decode())
    print(f"Injected {result.get('count', 0)} cookies")
    
    # Navigate
    conn = http.client.HTTPConnection("localhost", 9378)
    body = json.dumps({"userId": "walter", "sessionKey": session_key, "url": svc["url"]})
    conn.request("POST", "/tabs", body, {"Content-Type": "application/json"})
    resp = conn.getresponse()
    tab = json.loads(resp.read().decode())
    tab_id = tab.get("tabId")
    print(f"Tab: {tab_id} → {tab.get('url', svc['url'])}")
    return tab_id

# --- MAIN ---
print(f"=== {SERVICE.upper()} Browser ===")
print("Extracting cookies...")
cookies = extract_cookies()
print(f"Got {len(cookies)} auth cookies")

if not ensure_camoufox():
    print("ERROR: Camoufox not running on port 9378. Start it first.")
    sys.exit(1)

print("Injecting + navigating...")
tab_id = inject_and_navigate(cookies)

time.sleep(5)
print(f"\nDone. Tab ID: {tab_id}")
print(f"Session key: {session_key}")
print(f"Use Camoufox API to interact: /tabs/{tab_id}/snapshot, /tabs/{tab_id}/screenshot, etc.")
```

**See** `references/bumble-webtop-notes.md` for Bumble-specific details (cookie domains, SPA failure in Camoufox, conversation click patterns, profile data extraction).

