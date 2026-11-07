# browser-use × Camoufox — recette validée + benchmark (2026-08-11)

Boucle agentique LLM (`observe → act → extract`) dans un navigateur
anti-détection Camoufox. Prouvé en live : OneForma `/center/login` chargé,
8 éléments interactifs détectés, Turnstile contourné (`cfChallenge: false`),
titre « OneForma » renvoyé correctement.

## TL;DR

- **Version : browser-use 0.4.5** (ère Playwright native) — PAS 0.13.x+.
- **venv dédié** : `/root/.venv/bu-legacy`, `openai` épinglé à 1.85.0.
- **Piège critique** : pré-créer `context` + `page` AVANT `Agent(...)`,
  sinon boucle d'échec `Unknown permission: clipboard-read` ×3, steps=0.
- **Lire le résultat** : `history.final_result()`, pas step.result.

## Pourquoi 0.4.5 et pas la dernière

- `browser-use 0.13.x+` (CLI 3.0, Browser Harness) parle **CDP uniquement** :
  lance son propre Chromium, aucun backend juggler/geckodriver → impossible
  de piloter Camoufox (Firefox). `BrowserSession` est un modèle pydantic CDP.
- `browser-use 0.4.5` : `Browser = PatchrightBrowser | PlaywrightBrowser`
  (`browser_use/browser/types.py:23`). `Agent(browser=...)` accepte n'importe
  quel objet navigateur Playwright → Camoufox.

## Installation

```bash
/root/.venv/bu-legacy/bin/pip install "browser-use==0.4.5" camoufox "openai==1.85.0"
```

- `openai` doit être ~1.85 : 1.99.x casse (`cannot import name 'Function'`),
  1.35 trop vieux (`Cannot import 'ChatModel'`).
- Binaire Camoufox : `python -m camoufox fetch` (~/.cache/camoufox).
- Même cache que camoufox-js node — voir le piège partagé plus bas.

## Code de travail validé

```python
import asyncio, os
from camoufox.async_api import AsyncCamoufox
from browser_use import Agent
from browser_use.llm.openrouter.chat import ChatOpenRouter

PROXY = {"server": "http://127.0.0.1:1080"}  # tinyproxy -> NordVPN France

async def main():
    async with AsyncCamoufox(headless=True, humanize=False, geoip=False, proxy=PROXY) as camo:
        context = await camo.new_context()   # OBLIGATOIRE avant Agent
        page = await context.new_page()      # OBLIGATOIRE avant Agent
        llm = ChatOpenRouter(
            model="deepseek/deepseek-v4-flash",
            api_key=os.environ["OPENROUTER_API_KEY"],  # EXPLICITE, pas auto
        )
        agent = Agent(task="...", browser=camo, llm=llm)
        history = await agent.run(max_steps=8)
        print(history.final_result())        # la réponse finale est ICI
```

Pièges précis :
1. **Contexte pré-créé non négociable.** Sans lui, browser-use tente
   `Browser.new_context` avec permissions `clipboard-read/write` inconnues de
   Firefox → « Unknown permission: clipboard-read » répété 3× puis abandon
   (steps=0, final=None). Avec le contexte existant, log :
   « Using first browser_context available in existing browser ».
2. **`api_key=` explicite** sur ChatOpenRouter : il ne lit PAS
   OPENROUTER_API_KEY seul (cherche OPENAI_API_KEY → 502).
3. **Modèle sans suffixe `:free`** : `deepseek/deepseek-v4-flash:free` → 404
   « This model is unavailable for free » ; utiliser le slug payant.
4. **`final_result()`** : itérer `step.result` renvoie des chaînes vides.
5. DeepSeek : warning « use_vision not supported » — bénin, auto-désactivé.
6. `prompt` long = bons résultats ; tâche très concise → l'agent peut
   répondre sans naviguer (steps=0) : décrire l'action attendue en détail.

## Benchmark : boucle walter_browse vs boucle browser-use×Camoufox

Même cibles, même objectif (titres + prix), même proxy FR.

### Page HTML statique — books.toscrape.com

| | walter_browse (auto) | browser-use×Camoufox |
|---|---|---|
| Résultat | ÉCHEC (0 records, escalade brave-mac) | OK — 3 titres + prix exacts |
| Temps | 45,6 s gaspillés | 23,7 s |
| Tokens | ~0 | petit budget LLM |
| Cause | scorer JSON-only, ignore le HTML | lit le DOM |

### Page JSON/API — dummyjson.com/products

| | walter_browse (auto) | browser-use×Camoufox |
|---|---|---|
| Résultat | OK — 5 records | OK — 3 produits exacts ($9.99, $19.99, $14.99) |
| Temps | 0,52 s | 17,8 s |
| Tokens | ~0 | budget LLM |
| Verdict | imbattable sur son terrain | capable, surdimensionné |

### Conclusion

- **walter_browse gagne sur JSON/XHR** (SPA React, APIs, dashboards) :
  0,5 s, zéro token, records normalisés. Garder comme entrée par défaut.
- **browser-use×Camoufox gagne sur HTML statique + interaction** (login,
  clics, étapes) : lit le DOM, comprend la page, gère ce que le scorer
  JSON-only ne voit pas.
- Le gap de walter_browse est un **défaut de scoring** (pas de fallback DOM),
  pas une fatalité : un fallback DOM (hook React ou projection DOM) le comble.
- Les deux backends camoufox/webtop du routeur partagent le MÊME scorer
  JSON-only — l'escalade interne ne couvre pas le HTML statique.

## Piège partagé : cache Camoufox python vs node

`~/.cache/camoufox/version.json` est partagé entre :
- Python : `python -m camoufox fetch` → layout `official/stable` ;
- Node : `node .../camoufox-js/dist/__main__.js fetch` → autre version.

Lancer l'un casse l'autre (« CamoufoxNotInstalled » côté python, ou « Invalid
Extended Type at offset 0 » côté node). Après chaque bascule, relancer LE
fetch du consommateur utilisé.

## Réparation serveur camoufox-max (server-max.js)

- Fichier réel : `/root/.hermes/camoufox-max/server-max.js` (≠ node_modules).
- Port : env **`CAMOFOX_MAX_PORT`** (pas `PORT`).
- `/health` ment : `browserConnected:true` ne vérifie que `browser !== null`,
  pas sa vivacité. Si `/tab/new` → 500 « Target page, context or browser has
  been closed », redémarrer le serveur même si health semble OK.
- Une session morte côté requêtes = le serveur garde un contexte fermé ;
  redémarrage complet requis, pas une simple reconnexion.