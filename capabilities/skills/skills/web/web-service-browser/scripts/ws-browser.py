#!/usr/bin/env python3
"""Web Service Browser — one-shot cookie extract + inject + navigate.
Usage: python3 ws-browser.py [service] [--keep]
Services: gemini, suno, grok, chatgpt, claude, youtube, twitter, facebook, instagram

Options:
  --keep    Keep tab open after navigation (default: close after 5s)
"""
import http.client, json, time, hashlib, subprocess, sys
from Crypto.Cipher import AES

SERVICE = sys.argv[1] if len(sys.argv) > 1 else "gemini"
KEEP_TAB = "--keep" in sys.argv

SERVICES = {
    "gemini":   {"url": "https://gemini.google.com/app",    "domains": ["google", "gemini"]},
    "suno":     {"url": "https://suno.com",                 "domains": ["suno"]},
    "grok":     {"url": "https://grok.com",                  "domains": ["grok", "x.ai"]},
    "chatgpt":  {"url": "https://chatgpt.com",              "domains": ["openai", "chatgpt"]},
    "claude":   {"url": "https://claude.ai",                 "domains": ["claude", "anthropic"]},
    "youtube":  {"url": "https://youtube.com",               "domains": ["google", "youtube"]},
    "twitter":  {"url": "https://x.com",                     "domains": ["x.com", "twitter"]},
    "facebook": {"url": "https://facebook.com",              "domains": ["facebook"]},
    "instagram":{"url": "https://instagram.com",             "domains": ["instagram"]},
}

if SERVICE not in SERVICES:
    print(f"Unknown: {SERVICE}. Available: {', '.join(SERVICES.keys())}")
    sys.exit(1)

svc = SERVICES[SERVICE]
session_key = f"{SERVICE}-{int(time.time())}"

def get_key():
    r = subprocess.run(["vault", "get", "macos/brave_keychain_key"], capture_output=True, text=True, timeout=5)
    return r.stdout.strip().encode()

def extract_cookies():
    keychain_value = get_key()
    derived_key = hashlib.pbkdf2_hmac('sha1', keychain_value, b'saltysalt', 1003, dklen=16)
    subprocess.run(["ssh", "lucasjouvencon@100.127.150.1",
        "cp ~/Library/Application\\ Support/BraveSoftware/Brave-Browser/Default/Cookies /tmp/brave-cookies-latest.db"],
        check=True, capture_output=True, timeout=10)
    where = " OR ".join(f"host_key LIKE '%{d}%'" for d in svc["domains"])
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
    EXCLUDE = ('_ga', '_gcl', '_dd', 'ajs_', 'IR_', '_gat', '_gid')
    return [c for c in cookies if not any(c['name'].startswith(p) for p in EXCLUDE)]

def ensure_camoufox():
    try:
        conn = http.client.HTTPConnection("localhost", 9378, timeout=3)
        conn.request("GET", "/health")
        return conn.getresponse().status == 200
    except: return False

def inject_and_navigate(cookies):
    conn = http.client.HTTPConnection("localhost", 9378, timeout=10)
    body = json.dumps({"cookies": cookies})
    conn.request("POST", "/sessions/walter/cookies", body, {"Content-Type": "application/json"})
    resp = json.loads(conn.getresponse().read().decode())
    print(f"Injected {resp.get('count', 0)} cookies")
    conn = http.client.HTTPConnection("localhost", 9378, timeout=10)
    body = json.dumps({"userId": "walter", "sessionKey": session_key, "url": svc["url"]})
    conn.request("POST", "/tabs", body, {"Content-Type": "application/json"})
    tab = json.loads(conn.getresponse().read().decode())
    tab_id = tab.get("tabId")
    print(f"Tab: {tab_id} -> {tab.get('url', svc['url'])}")
    return tab_id

def close_tab(tab_id):
    try:
        conn = http.client.HTTPConnection("localhost", 9378, timeout=5)
        conn.request("DELETE", f"/tabs/{tab_id}?userId=walter")
        conn.getresponse().read()
        print(f"Tab {tab_id[:8]} closed")
    except: pass

print(f"=== {SERVICE.upper()} ===")
print("Extracting cookies from Mac Brave...")
cookies = extract_cookies()
print(f"Got {len(cookies)} auth cookies")
if not ensure_camoufox():
    print("ERROR: Camoufox not running on port 9378")
    sys.exit(1)
print("Injecting + navigating...")
tab_id = inject_and_navigate(cookies)
time.sleep(5)
print(f"\nDone. Tab: {tab_id} | Session: {session_key}")
if not KEEP_TAB:
    print("Use --keep to keep tab open. Closing in 5s...")
    time.sleep(5)
    close_tab(tab_id)
