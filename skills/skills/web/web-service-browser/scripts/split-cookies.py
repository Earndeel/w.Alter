#!/usr/bin/env python3
"""Split cookies by service domain. Run on HOST (has vault + pycryptodome).
Input: /tmp/all-raw-cookies.txt (SSH-extracted from Mac Brave)
Output: /tmp/cookies-{gemini,suno,grok,...}.json
"""
import hashlib, json, sys
from Crypto.Cipher import AES

keychain_value = b'{{bw:W.Alter · macos:field:brave_keychain_key}}'
dk = hashlib.pbkdf2_hmac('sha1', keychain_value, b'saltysalt', 1003, dklen=16)

def dec(h):
    e = bytes.fromhex(h)
    if e[:3] == b'v10': e = e[3:]
    elif e[:4] == b'v11': e = e[4:]
    d = AES.new(dk, AES.MODE_CBC, e[:16]).decrypt(e[16:])
    p = d[-1]
    if 1 <= p <= 16 and all(b == p for b in d[-p:]): d = d[:-p]
    c = d[16:] if len(d) > 16 else d
    return bytes(b for b in c if 32 <= b <= 126).decode('ascii', 'replace')

with open('/tmp/all-raw-cookies.txt') as f:
    raw = f.read().strip()

cookies = []
for line in raw.split('\n'):
    p = line.split('|')
    if len(p) < 7: continue
    v = dec(p[2])
    if not v or len(v) < 2: continue
    c = {'name': p[1], 'value': v, 'domain': p[0], 'path': p[3],
         'secure': p[4] == '1', 'httpOnly': p[5] == '1'}
    ex = int(p[6]) if p[6] else 0
    if ex > 0: c['expires'] = int((ex / 1000000) - 11644473600)
    cookies.append(c)

EX = ('_ga', '_gcl', '_dd', 'ajs_', 'IR_', '_gat', '_gid')
cookies = [c for c in cookies if not any(c['name'].startswith(x) for x in EX)]

def filt(*domains):
    return [c for c in cookies if any(d in c['domain'] for d in domains)]

SERVICES = {
    'gemini': ('google', 'gemini'),
    'suno': ('suno',),
    'grok': ('grok', 'x.ai'),
    'twitter': ('x.com', 'twitter'),
    'chatgpt': ('openai', 'chatgpt'),
    'claude': ('claude', 'anthropic'),
}

for name, domains in SERVICES.items():
    cs = filt(*domains)
    with open(f'/tmp/cookies-{name}.json', 'w') as f:
        json.dump(cs, f)
    print(f'{name}: {len(cs)} cookies')

# Also save merged + deduplicated
all_c = []
seen = set()
for c in cookies:
    k = (c['domain'], c['name'])
    if k not in seen:
        seen.add(k)
        all_c.append(c)
with open('/tmp/cookies-all.json', 'w') as f:
    json.dump(all_c, f)
print(f'Total unique: {len(all_c)}')
