---
name: earndeel-twitter-ai-list
description: "Check Monsieur's X/Twitter AI list — scrape posts, synthesize. 'Mon Twitter AI' = sa liste Artificial Intelligence, pas son profil."
version: 1.0.0
author: W.Alter
triggers:
  - checker mon twitter ai
  - twitter ai
  - ma liste ai
  - check twitter
  - checker x
metadata:
  hermes:
    tags: [twitter, x, list, ai, earndeel]
---

# Earndeel's Twitter AI List

**"Mon Twitter AI"** = la liste **Artificial Intelligence** de @earndeel, PAS son profil.

## Identifiants

| Info | Valeur |
|------|--------|
| Handle | @earndeel |
| User ID | 1575827511124295680 |
| Liste AI | https://x.com/i/lists/1908397080189526287 |
| Membres liste | 41 |
| Statut | Épinglée, Premium+, certifié |

## Autres listes de @earndeel

| Liste | Membres | Épinglée |
|-------|---------|----------|
| Artificial intelligence | 41 | ✅ |
| Gaming | 2 | ✅ |
| Finance | 1 | ❌ |
| Geopolitics | 3 | ❌ |
| Robotic | 9 | ❌ |
| Technology | 10 | ❌ |

## Pipeline de scraping

### 1. Vérifier Camoufox
```bash
docker exec webtop bash -c 'curl -s http://localhost:9378/health'
```

### 2. Cookies (extraire du Mac Brave)
```bash
# Copier DB fraîche
ssh lucasjouvencon@100.127.150.1 "cp ~/Library/Application\ Support/BraveSoftware/Brave-Browser/Default/Cookies /tmp/brave-cookies-latest.db"

# Extraire cookies X
ssh lucasjouvencon@100.127.150.1 "sqlite3 /tmp/brave-cookies-latest.db \"SELECT host_key, name, hex(encrypted_value), path, is_secure, is_httponly, expires_utc FROM cookies WHERE host_key LIKE '%x.com%' OR host_key LIKE '%twitter%'\"" > /tmp/x-raw-cookies.txt

# Décrypter sur host (vault get macos/brave_keychain_key + PBKDF2 + AES-128-CBC)
python3 /tmp/decrypt-cookies.py  # → /tmp/cookies-x.json

# Pousser dans container
docker cp /tmp/cookies-x.json webtop:/tmp/cookies-x.json
```

### 3. Injecter + naviguer vers la liste
```python
import http.client, json, time

with open('/tmp/cookies-x.json') as f:
    cookies = json.load(f)

h = http.client.HTTPConnection('localhost', 9378, timeout=10)
h.request('POST', '/sessions/walter/cookies', json.dumps({'cookies': cookies}), {'Content-Type': 'application/json'})
h.getresponse().read()

sk = 'ai-list-' + str(int(time.time()))
h2 = http.client.HTTPConnection('localhost', 9378, timeout=15)
h2.request('POST', '/tabs', json.dumps({
    'userId': 'walter', 'sessionKey': sk,
    'url': 'https://x.com/i/lists/1908397080189526287'
}), {'Content-Type': 'application/json'})
```

### 4. Scraper avec scroll JS (PAS l'API scroll qui timeout)
```python
def scroll_js(tid, sk, amount=1500):
    h = http.client.HTTPConnection('localhost', 9378, timeout=20)
    h.request('POST', f'/tabs/{tid}/evaluate', json.dumps({
        'userId': 'walter', 'sessionKey': sk,
        'expression': f'window.scrollBy(0, {amount})'
    }), {'Content-Type': 'application/json'})
    h.getresponse().read()

# Pattern: snapshot → extract → scroll → repeat
# Regex: r'article "([^"]{50,})"'
# Dedup key: first 80 chars of article text
```

### 5. Synthétiser et envoyer
- Synthèse structurée par sujet/impact
- Envoyer sur Telegram si demandé (HTML parse_mode, 4096 max)
- Sauvegarder les posts scrapés dans un fichier JSON pour référence

## Limitations
- X virtual scrolling limite à ~20 posts par session
- Scroll API timeout → utiliser JS evaluate (`window.scrollBy`)
- Pour 50+ posts : itérer sur plusieurs sessions ou utiliser X API payante
- Cookies expirent ~1 semaine, re-extracter si "Sign in" visible

## Pitfalls
- **Mauvais tab ID** : toujours capturer le tab_id depuis la réponse POST /tabs
- **Tabs fermés** : vérifier avec GET /tabs?userId=walter avant de scraper
- **Article regex** : le format est `article "texte..."` avec guillemets doubles
- **Session key** : doit matcher entre navigate et snapshot/scroll/evaluate
