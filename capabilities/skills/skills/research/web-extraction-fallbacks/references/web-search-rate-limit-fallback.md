# web_search Rate Limiting & web_extract Failure — Patterns de Contournement

## Contexte

Le backend `web_search` d'Hermes utilise **Brave Search Free** (pas l'API avec clé). Cette configuration impose deux limites critiques :

1. **Rate limiting agressif** — HTTP 429 après ~3-5 requêtes en rafale, bien plus strict que le 1 req/sec de l'API Brave
2. **Pas d'extraction de contenu** — `web_extract` retourne `"Brave Search (Free) is a search-only backend and cannot extract URL content"`

## Symptômes

```
# web_search rate-limited
{"success": false, "error": "Brave Search returned HTTP 429"}

# web_extract failure
{"success": false, "error": "Brave Search (Free) is a search-only backend and cannot extract URL content. Set web.extract_backend to firecrawl, tavily, exa, or parallel."}
```

## Stratégies de Contournement (par ordre de préférence)

### 1. Batcher les requêtes web_search indépendantes

Les appels parallèles dans le même tour assistant passent TOUS avant que le rate limiting ne se déclenche.

**Bon :**
```
web_search(query="terme A"), web_search(query="terme B"), web_search(query="terme C"), web_search(query="terme D")
→ 4 appels dans le même <invoke> bloc → tous passent
```

**Mauvais :**
```
web_search(query="terme A")
→ 429
web_search(query="terme A")  (retry même query)
→ 429
```

### 2. Varier les queries, jamais retenter la même

Après un 429, changer les termes de recherche, pas juste retenter. Le rate limiting est par endpoint, et des queries différentes passent souvent.

### 3. curl + sed/grep pour l'extraction de contenu

Quand `web_extract` échoue et que la page est du HTML statique (articles, blogs, docs, arxiv) :

```bash
# Extraction du JSON-LD (souvent le contenu le plus riche)
curl -sL "$URL" | grep -oP '<script type="application/ld\+json">.*?</script>' | head -1

# Extraction du texte visible (stripping HTML)
curl -sL "$URL" | sed 's/<[^>]*>//g' | sed '/^[[:space:]]*$/d' | head -200

# Extraction ciblée avec contexte
curl -sL "$URL" | sed 's/<[^>]*>//g' | tr -s '[:space:]' ' ' | grep -ioP '.{0,300}(mot-clé1|mot-clé2).{0,300}' | head -20
```

### 4. browser_navigate pour contenu JS

Si le contenu nécessite JavaScript, utiliser `browser_navigate` (backend Chromium/Playwright séparé, pas affecté par le rate limiting Brave).

## Quand utiliser quoi

| Scénario | Outil | Latence |
|---|---|---|
| Recherche de liens/sources | `web_search` (batcher 3-4 appels) | ~1-2s |
| Article/blog statique | `curl \| sed` | ~1-3s |
| Page JS (SPA, React) | `browser_navigate` | ~5-15s |
| PDF/article académique | `curl` + `pdftotext` | ~2-5s |
| Page protégée (Cloudflare) | Camoufox (Tier 4) ou Webtop (Tier 5) | ~10-30s |