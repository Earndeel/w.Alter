---
name: x-research-pipeline
description: "X/Twitter research pipeline — scraping + PostgreSQL + analyse. Deux modes : recherche rapide (~3min) et veille async (cron). Anti-bot safe. Inclut stratégie de pertinence, cookie management, et export Notion."
version: 2.0.0
author: walter
tags: [x, twitter, scraping, research, postgresql, sentiment, veille, anti-bot, notion]
---

# X Research Pipeline

Scraping X → PostgreSQL → Analyse → Notion. Deux modes : recherche (on-demand, ~3min) et veille (cron async).

## Triggers

- User asks to analyze opinions/sentiment on X about a topic
- User asks to research what people think about X on Twitter
- User wants to monitor a topic/brand/person on X
- User asks to extract posts, prompts, or content from an X account
- User asks to analyze features/releases/updates of a company or product → start with `x_search` for their handle; X posts have dates, engagement metrics, and direct quotes that web articles lack

## Quick Start

```bash
# Recherche rapide (topic)
python3 ~/.hermes/scripts/x_research_scrape.py "Gemini 3.5 Flash" --mode recherche --max-posts 70 --threads 10

# Profil spécifique (use from: syntax)
# See Profile Scraping section below

# Veille async (cron)
python3 ~/.hermes/scripts/x_research_scrape.py "sujet" --mode veille --max-posts 30 --threads 5
```

## Architecture (3 phases, ~2-3 min)

```
Phase 1: X search (4 requêtes, ~20s)
  → f=top (pertinence) + f=live (récence)
  → ~40 posts triés par engagement

Phase 2: Google site:x.com (3 requêtes, ~15s)  
  → Pertinence pure (ce que Google juge important)
  → URLs complémentaires

Phase 3: Top threads (10 requêtes, ~20s)
  → Posts les plus engageants → scraper replies
  → ~70 commentaires

Phase 4: Analyse → PG (instant)
  → Sentiment, thèmes, langues, rapport

Total: ~17 requêtes X, ~2-3 min, ~110-150 posts
```

## Pertinence vs Récence

Le scraping X trie par défaut par récence (`f=live`). Pour la pertinence :

| Méthode | Ce qu'elle donne | Comment |
|---|---|---|
| `f=top` | Posts les plus engageants/pertinents | X search parameter |
| `min_faves:N` | Posts avec N+ likes | Filtre X natif |
| `site:x.com` via Google | Posts les plus référencés | Pertinence Google |
| Profils ciblés | Posts des influenceurs | `from:@handle` |
| Multi-requêtes | Couverture angles différents | Variance keywords |

**Pour un profil spécifique**, utiliser `from:handle` au lieu de recherche générale :
```python
# Direct profile scraping (scroll the profile page)
page.goto("https://x.com/aimikoda")
# X search filtered to user
page.goto("https://x.com/search?q=from%3Aaimikoda&src=typed_query&f=top")
```

## PostgreSQL

Schema: `x_research` dans la base `hindsight` (container `hindsight-pg`)
**Vérifier l'IP à chaque session** : `docker inspect hindsight-pg --format '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}'`

| Table | Rôle |
|---|---|
| `x_research.searches` | Une ligne par recherche |
| `x_research.posts` | Tous les posts (dedup par text_hash) |
| `x_research.themes` | Thèmes configurables par recherche |
| `x_research.snapshots` | Historique pour veille |

Index: 13 index dont FTS (`tsv tsvector` + GIN), trigger auto-update.

## Scripts

Tous dans `~/.hermes/scripts/` :

| Script | Rôle |
|---|---|
| `x_research_db.py` | Connexion PG, CRUD, requêtes analytiques |
| `x_research_analyze.py` | Sentiment (keyword ~80%), thèmes, langues, rapport |
| `x_research_scrape.py` | Pipeline complet: scraping → analyse → PG |

## Anti-bot Strategy

| Règle | Valeur | Pourquoi |
|---|---|---|
| Délai entre requêtes | 2-4s (random) | X bloque < 2s |
| Nouveau contexte Playwright | Par requête X | Cookies frais, fingerprint propre |
| Requêtes par session | Max 17 | Sous le rate-limit (~10/min) |
| Scroll lent | 2-3s entre scrolls | Comme un humain |
| Pas de pattern fixe | Random delays | Timing prévisible = détecté |

**NE JAMAIS scraper via Mac Brave** — utiliser VPS Playwright + cookies exportés.

## Cookie Management

Cookies X auth dans `/tmp/x_cookies.json` (auth_token, ct0, twid). Valables ~30 jours.

Export depuis Mac Brave (bref instant, ~2s) :
```python
from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp("http://localhost:9222")
ctx = browser.contexts[0]
x = [c for c in ctx.cookies() if 'x.com' in c.get('domain','')]
import json; json.dump(x, open('/tmp/x_cookies.json','w'), indent=2)
pw.stop()
```

Injection dans Playwright VPS :
```python
with open("/tmp/x_cookies.json") as f:
    cookies = json.load(f)
pw_cookies = [{"name": c["name"], "value": c["value"], "domain": c["domain"],
               "path": c.get("path","/"), "secure": c.get("secure",True),
               "httpOnly": c.get("httpOnly",False)} for c in cookies]
context.add_cookies(pw_cookies)
```

## Requêtes PG directes

```sql
-- Sentiment breakdown
SELECT sentiment, COUNT(*), AVG(likes) FROM x_research.posts WHERE search_id=1 GROUP BY sentiment;

-- Top posts négatifs
SELECT author, likes, text FROM x_research.posts WHERE search_id=1 AND sentiment='negative' ORDER BY likes DESC LIMIT 5;

-- Full-text search
SELECT author, likes, text FROM x_research.posts WHERE tsv @@ plainto_tsquery('simple', 'benchmark') ORDER BY likes DESC LIMIT 10;

-- Par langue
SELECT language, COUNT(*) FROM x_research.posts WHERE search_id=1 GROUP BY language ORDER BY COUNT(*) DESC;

-- Historique veille
SELECT snapshot_at, positive_pct, negative_pct FROM x_research.snapshots WHERE search_id=1 ORDER BY snapshot_at;
```

## Export vers Notion

After scraping, create a Notion page with structured content:
- Callouts for profile summary
- Code blocks for prompts
- Images from X (pbs.twimg.com URLs work as external images)
- Quotes for original post text
- Toggles for technical explanations
- **Video blocks** via Cloudflare Worker + R2 (see `references/notion-video-embedding.md`)
- **Limit: 100 blocks per API call** — paginate if more needed

See `references/notion-export.md` for template.

## Quick handle monitor (zero credentials)

For "give me the last N posts from @handle" without xurl/x_search/scraping — `nitter.net/<handle>/rss` works as of June 2026 (no auth, no cookies, ~1s response, ~20 items). See `references/nitter-rss-fallback.md` for code, instance status, and caveats. Use this for daily veille or quick news digests; escalate to `x_search` or full pipeline for engagement/replies/sentiment.
See `references/notion-video-embedding.md` for video embedding pipeline.
See `references/cookie-conversion.md` for yt-dlp cookie conversion.
See `references/pg_schema.sql` for the full database schema.

## PG Container IP

The hindsight-pg container IP changes on restart. **Always check at session start:**
```bash
docker inspect hindsight-pg --format '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
```
Then update `PG_DSN` in `~/.hermes/scripts/x_research_db.py` if needed.

## Architecture anti-bot

Le scraping X est un jeu du chat et de la souris. Notre avantage : cookies réels + IP réelle (Mac via Tailscale exit node).

| Signal anti-bot | Notre statut |
|---|---|
| Authentification | ✅ cookies auth_token + ct0 depuis Mac Brave |
| IP / géolocalisation | ✅ IP Mac via Tailscale exit node (VPS route via Mac) |
| User-Agent | ✅ Chrome réel (Playwright headless) |
| Rate limiting | ✅ ~17 requêtes/session, bien sous le seuil |
| WebGL/Canvas fingerprint | ⚠️ Pas de GPU → différent mais X ne vérifie pas ça |

Règles :
- Délai randomisé 2-4s entre requêtes
- Nouveau contexte Playwright par requête X
- Max ~15 requêtes par session, pause 60-120s si plus
- Cookies valables ~30 jours, re-exporter quand 0 posts

## Mode RECHERCHE (on-demand, ~2-3 min)

```
Phase 1: X f=top + f=live (4 requêtes) → ~40 posts pertinents
Phase 2: Google site:x.com (3 requêtes) → URLs complémentaires  
Phase 3: Top 10 threads (10 requêtes) → ~70 replies
Phase 4: Analyse → PG (x_research schema)
Total: ~17 requêtes X, ~3min, ~110-150 posts
```

### Phase 1 : X search (pertinence)
- `f=top` trie par pertinence/engagement (pas récence)
- `f=live` pour les réactions fraîches
- `min_faves:5` pour filtrer le bruit
- Nouveau contexte Playwright par requête

### Phase 2 : Google site:x.com (pertinence pure)
- Google indexe X et trie par pertinence
- Scrapling ou Playwright pour extraire les URLs
- Souvent retourne 0 (Google bloque le scraping) — X search compense

### Phase 3 : Threads (commentaires)
- Trier les posts par engagement, prendre les top 10 avec URL
- Scraper chaque thread (post + replies)
- Les commentaires contiennent souvent l'opinion la plus nuancée

### Phase 4 : Analyse + Stockage
- Sentiment keyword-based (~80% précision)
- Détection thèmes par mots-clés configurables
- Détection langue par regex (ja, zh, fr, tr, ru, es, de, ko, ar)
- Insert PG + snapshot

## Mode VEILLE (async, cron 2x/jour)

```
Cron job (09h, 18h)
  ↓
1. X f=top : "sujet" (1 requête, ~5s)
2. X f=live : "sujet" (1 requête, ~5s)
3. Compare avec dernier snapshot
4. Si nouveau pic d'engagement → alerte Telegram
5. Insert PG + snapshot
```

## Stratégie de requêtes (sans x_search)

Pour la pertinence sans x_search :
- `f=top` au lieu de `f=live` → trie par engagement
- Google `site:x.com` → pertinence pure
- Multi-requêtes avec angles différents (neutre, positif, négatif, comparatif, technique)
- Seuil d'engagement minimum (min_faves:5)
- Scraping de profils influents ciblés

## Organisation multi-sujets

Chaque recherche = son propre JSON, sa propre analyse, son propre rapport.
```python
RECHERCHES = {
    "sujet_1": {"queries": [...], "max_posts": 200, "time_range": "7d"},
    "sujet_2": {"queries": [...], "max_posts": 200, "time_range": "7d"},
}
```

## Pitfalls

- **Google site:x.com retourne 0** → normal, Google bloque parfois le scraping. X search compense.
- **Cookies expirent** → re-exporter depuis Brave si 0 posts. Délai ~30 jours.
- **PG container IP change** → vérifier avec `docker inspect hindsight-pg`. Actuellement 172.17.0.4.
- **Sentiment keyword-based ≈80%** → suffisant pour aperçu, pas pour rapport académique.
- **Posts neutres dominent** → normal, la majorité des posts X sont factuels/neutres.
- **Biais engagement** → les posts négatifs ont 23x plus d'engagement (mesuré). L'opinion X ≠ opinion réelle.
- **yt-dlp avec cookies X** → utiliser les URLs de posts (pas les IDs de thumbnails vidéo). Format Netscape pour les cookies.
- **Nitter RSS pour handle-only veille** → quand on veut juste les ~20 derniers posts d'un compte spécifique (ex: @NousResearch, @Teknium), `https://nitter.net/<handle>/rss` fonctionne en juin 2026 sans cookies, sans auth, sans anti-bot. Retourne texte + timestamp + lien en ~1s. **Limites** : ne donne pas les replies/comments, ne permet pas de filtrer strictement à `from:<handle>` (peut inclure des interactions), pas d'engagement metrics (likes/RT). Pour replies ou analyse d'engagement → x_search ou pipeline complet. Autres instances Nitter (privacydev.net, poast.org) sont mortes. Pages HTML Nitter (profil, status) renvoient empty body.
- **yt-dlp ne trouve pas la vidéo** → vérifier que l'URL est bien le post (status/ID) et pas le thumbnail (amplify_video_thumb/ID).
- **f=top vs f=live** → top = pertinence (posts importants), live = récence (derniers posts). Les deux sont nécessaires.
- **Threads = l'or de l'analyse** → les commentaires contiennent souvent l'opinion la plus nuancée. Toujours scraper les top threads.
- **Profil ≠ recherche** → pour un compte spécifique, utiliser `from:handle` pas une recherche générale
- **Features/releases ≠ sentiment** → quand l'utilisateur demande les features d'un produit, commencer par `x_search` sur leur handle officiel (pas le pipeline de scraping complet). Les posts X ont des dates, métriques d'engagement et citations directes que les articles web n'ont pas. Ensuite seulement, compléter avec web search pour la profondeur.
- **x_search en premier pour l'analyse produit** → `x_search(query="from:handle")` donne les annonces officielles avec dates. Utiliser les handles multiples si la compagnie en a (ex: @higgsfield + @higgsfield_ai). Passer à Brave/web search seulement si X ne suffit pas.
- **x_search en premier pour les news d'une personne** → quand l'utilisateur demande les news/récentes activités d'une personnalité active sur X, utiliser `x_search(query="from:handle")` AVANT web_search. Web_search retourne des articles génériques et datés ; x_search donne les posts réels avec dates, engagement, et contexte immédiat. Exemple : "check les news de Pliny" → web_search a donné des résultats TIME/génériques, x_search a donné le dernier jailbreak en date avec techniques exactes. Compléter avec web_search seulement si X ne couvre pas le sujet.
- **yt-dlp: utiliser les URLs de posts, pas les thumbnail IDs** → les `amplify_video_thumb/<ID>/img/` ne sont PAS les post IDs. Le bon format: `x.com/<handle>/status/<post_id>`
- **yt-dlp cookies Netscape** → exporter depuis `/tmp/x_cookies.json` vers format Netscape pour yt-dlp (voir references/cookie-conversion.md)
- **Webtop Chromium crash sur X** → trop lourd. Utiliser VPS Playwright direct.
- **Scrapling/StealthyFetch sans cookies** → login wall. Toujours injecter les cookies d'abord.
- **compute_stats crash si 0 posts** → vérifier `len(posts) > 0` avant d'appeler `insert_snapshot`. Le code `x_research_db.py` doit gérer le cas où `total_posts=0` dans `compute_stats()` (division par zéro sur `sum(likes)/total`).
- **Profil scraping testé et validé** → `from:handle` + scroll profil + `from:handle` sur X search f=top. ~50 posts en ~2min. Voir session 20/05/2026 @aimikoda.
- **Notion: vidéos inline coûtent de l'argent** → R2+Worker fonctionne mais Lucas ne veut PAS payer Cloudflare pour ça. Utiliser les **bookmarks** (gratuit, rich preview) ou YouTube/Loom (gratuit, inline). Voir `references/notion-video-embedding.md`.
