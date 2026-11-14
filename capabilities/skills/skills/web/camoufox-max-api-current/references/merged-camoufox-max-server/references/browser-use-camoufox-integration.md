# Browser-use × Camoufox — Integration Validée (2026-08-11)

Intégrer la boucle agentique browser-use (actions décidées par LLM) SUR le
navigateur anti-détection Camoufox — le combo stealth + interaction scriptée.

## Verdict de compatibilité (testé en conditions réelles)

| Version browser-use | Protocole | Peut piloter Camoufox (Firefox) |
|---|---|---|
| 0.13.7 (CLI 3.0, celle du tweet Nous Research) | CDP-only (Browser Harness, Chromium intégré) | ❌ NON — aucun backend firefox/juggler/geckodriver |
| 0.4.5 (ère Playwright-native) | Playwright (`Browser = PatchrightBrowser \| PlaywrightBrowser`) | ✅ OUI — accepte un navigateur externe |

**Règle** : le mode Browser Use CLI 3.0 du tweet (~-48-66% tokens) ne peut PAS
utiliser Camoufox. Le gain du tweet est une économie d'orchestration (1 outil au
lieu de 12 dans le payload Hermes), pas une économie de boucle interne — ne pas
essayer de l'adapter à Camoufox.

## Environnement exact (contraintes strictes)

```bash
# venv isolé dédié — PAS le venv Hermes
python3 -m venv /root/.venv/bu-legacy
/root/.venv/bu-legacy/bin/pip install "browser-use==0.4.5" camoufox
/root/.venv/bu-legacy/bin/pip install "openai==1.85.0"   # pin OBLIGATOIRE:
# openai trop récent casse browser-use 0.4.5 (Function type déplacé)
```

- Clé API : `ChatOpenRouter` de la 0.4.5 ne lit PAS `OPENROUTER_API_KEY`
  automatiquement — la passer explicitement : `api_key=os.environ["OPENROUTER_API_KEY"]`
  ET faire `os.environ.setdefault("OPENAI_API_KEY", openrouter_key)` (le
  constructeur retombe sur OPENAI_API_KEY). Charger depuis `/root/.hermes/.env`.
- Modèle : `model="deepseek/deepseek-v4-flash"` (slug PAYANT — le `:free`
  n'existe plus et échoue silencieusement).

## Piège CRITIQUE : permissions clipboard (Firefox)

Sans contexte Playwright pré-créé, browser-use tente `Browser.new_context()` avec
ses permissions par défaut incluant `clipboard-read` — **Firefox les refuse** :

```
setup_new_browser_context failed: Browser.new_context: Unknown permission: clipboard-read
→ 3 échecs consécutifs → "Stopping due to 3 consecutive failures" (steps=0, final=None)
```

**Fix** : créer context + page AVANT d'instancier l'Agent, et passer le navigateur
Camoufox (`browser=camo`) :

```python
from camoufox.async_api import AsyncCamoufox
from browser_use import Agent
from browser_use.llm.openrouter.chat import ChatOpenRouter

PROXY = {"server": "http://127.0.0.1:1080"}   # sortie FR via nordvpn-proxy

async with AsyncCamoufox(headless=True, humanize=True, geoip=False, proxy=PROXY) as camo:
    context = await camo.new_context()        # CRITIQUE : contexte prêt AVANT Agent
    page = await context.new_page()
    llm = ChatOpenRouter(model="deepseek/deepseek-v4-flash", api_key=KEY)
    agent = Agent(task=tâche, browser=camo, llm=llm)   # browser= l'instance Camoufox
    history = await agent.run(max_steps=8)
    final = history.final_result()            # réponse finale — PAS step.result
```

- L'agent logue `🌎 Using first browser_context available` → le Camoufox est bien
  le navigateur piloté.
- `geoip=False` + proxy manuel évite le warning LeakWarning.
- Extraire la réponse avec `history.final_result()` (les champs `step.result` ne
  contiennent pas la réponse consolidée).

## LLM : boucle et extraction séparables

- `llm=` = base_model, pilote la boucle (choix des actions) — obligatoire.
- `page_extraction_llm=` = extraction_model, utilisé par `extract_structured_data`
  — par défaut = même modèle ; le séparer (ex. gemini flash lite) réduit le coût.
- `planner_llm=` optionnel (plan long terme).

## Benchmark (même cible, même contrat, proxy FR)

| Cible | walter_browse (auto) | browser-use×Camoufox |
|---|---|---|
| JSON/API (dummyjson) | ✅ 5 records, 0,52 s, 0 token | ✅ 17,8 s, ~LLM |
| HTML statique (books.toscrape) | ❌ 0 record (scorer JSON/XHR-only) | ✅ 3 titres+prix exacts, 23,7 s |

Conclusion : complémentaires. walter_browse = boucle de routage au sommet (0
token sur son terrain JSON), browser-use×Camoufox = boucle d'actions dans la page
pour HTML/interaction. Position dans la stack : backend escalade #3 après
camoufox-max, avant webtop-cdp. Le gap scorer HTML (JSON-only) de walter_browse
est un bug de conception connu — un fallback DOM le résoudrait.

Scripts : `/root/.hermes/scripts/test_browser_use_camoufox.py` (compat),
`/root/.hermes/scripts/bench_browser_use.py` (bench comparatif),
`/root/.hermes/scripts/start-camoufox-max.sh` (démarrage serveur).