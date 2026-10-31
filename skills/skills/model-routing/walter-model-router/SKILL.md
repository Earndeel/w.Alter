---
name: walter-model-router
description: "Use when choosing which AI model or provider W.Alter should use for a task, checking live leaderboards, prices or the owner's AI subscriptions, explaining or tuning Walter Router (tasks, weights, preferences, alerts, library page), or analysing its 48 h cycle."
version: 4.3.0
author: W.Alter
metadata:
  hermes:
    tags: [router, model-selection, pricing, benchmarks, subscriptions, postgresql, openrouter, kie, codex]
    related_skills: [aa-pareto-model-optimizer, kie-ai-api-direct, model-router-intelligence-loop]
---

# Walter Router

Module `/walter/router` (also reachable as `/opt/walter-router`), command `walter-router` on the PATH. Data: schema
`models` in PostgreSQL 127.0.0.1:5433 db `hindsight` (password only in ~/.pgpass; every table and view is commented).
Read first: `/walter/router/README.md` (current state: layout, how a choice is made, consumers, access, rules), then
`docs/README.md` (documentation index), `docs/reference/DATABASE.md` (all SQL fields), `docs/DATA.md` (provenance), `docs/TIERS.md` (text tiers), `docs/HISTORY.md` (dated decisions).
The old store (schema `walter_router`, fixed weight vectors, router_matrix.json) is retired: never use it.

## Ask the router — never hardcode a model
- `walter-router pick <task> [--level L1|L2|L3] [--role R] [--require unrestricted|open_weights|video_input]` — model,
  provider order with prices, fallbacks (`video_input`: e.g. `pick vision --require video_input` to analyse a video;
  there is no video-analysis task, no satisfying benchmark).
  `walter-router tasks` lists the task keys (42, incl. medical, legal, engineering, finance, strategy, cybersecurity,
  science, long_context, writing, music, vision, video roles…).
- `walter-router route "<demande>" [--context "<what the conversation was about>"]` — the decision model (d1-ultra,
  then Mercury Decide free, then Clef) classifies the request (with `--context` when it depends on earlier turns,
  e.g. « fais la suite »), then the decision with its execution routes and each route's price per million tokens.
  Not called when `--task` (and `--level` for general) are given. `classify` = intent only.
- `walter-router dossier <task>` — the evidence behind a choice; `walter-router library` — the whole table (also the
  library page, behind Cloudflare Access).
- Text calls from modules or agents: walter-llm (127.0.0.1:8894, OpenAI-compatible, `model` = a router task, per-agent
  token). Agents: the same tools in every runtime — walter_route, walter_run (text sub-agent or media generation),
  walter_decide (the decision model for any quick choice), walter_plans (Hermes
  plugin; walter MCP for Claude Code / Codex / DSH), plus walter_verdict / walter_feedback in Hermes. walter_route and
  walter_run take `conversation`, the same line as `--context`. What agents can ask for (levels, specialities,
  generation, constraints) is `walter-router brief`, generated from the database and given to every agent (Hermes
  prompt section, MCP instructions, Codex / DSH profiles): edit tasks/roles, never the prompt.
- Doing the job: `walter-router run` (JSON spec on stdin: goal, context, task, level, or model + provider when the
  owner names them — run exactly as named or refused, never substituted; media: role, image_urls…). Media costs
  money, only on request; `walter-router generate "<demande>" --task …` remains the direct media command.
- `walter-router ask "<question>" --option a="…" --option b="…"` — the decision model for any choice.

## How a choice is made (read the README for details)
- research/ fetches 16 sources by category (`walter-router research image|video|text|audio|memory|decision|prices|
  hosts|plans [--analyse]`); analysis/ ranks each task on its weighted boards among the models Walter can run; the
  owner's pins and roles always win; a better model is only PROPOSED on Telegram with buttons.
- Route order: subscription at its cost price while its weekly quota < 90 %, Kie if reliable and not much dearer,
  OpenRouter on the cheapest usable host the router imposes (provider order passed by walter-llm and by Hermes'
  provider_routing.models). Media: the same model on its next provider; another model only if declared.
- plan/: the owner's subscriptions (`walter-router plans list|set|retire`, never invent a plan or a price; billing
  mails become proposals; plan news become notices).

## Checks
- `walter-router health`, `status`, `review`, `alerts --all`; tests `cd /walter/router && venv/bin/python -m pytest -q`.
- Before calling a provider "cheapest", compare every provider and host at equal settings (`models.offers`,
  `models.best_endpoints`, subscription cost price in `models.latest_subscription_costs`).

## Pitfalls
1. Next.js flight data prefixes change (`c:` → `d:`): strip any single-letter prefix; reject a suspiciously tiny parse.
2. OpenRouter chat ids use dots (`openai/gpt-6-luna`), router ids dashes (`gpt-6-luna`); `pick` returns `openrouter_id`.
3. OpenRouter prices are $/token (× 1e6 for $/M); media prices come from each model page `displayPricing`.
4. Kie has no global discount; Kie Claude and Kie GPT degrade under load — the router demotes a route failing ≥ 50 % of
   its last runs.
5. A board that disappears is kept 21 days from its last snapshot and raises `board_down`.
6. Never run `bw unlock` yourself to reach provider keys: use `walter-secret` (shared Bitwarden session).

## Research reference — sources and pitfalls (still valid)

Kept from the August collectors: how each source must be read and checked. The live readers are in
`/walter/router/research/` (AA through the Next.js data of its pages, no API key needed for the router's own sources).

### AA API v2
- `GET https://artificialanalysis.ai/api/v2/data/llms/models` with `x-api-key` header
- Key in vault: `artificialanalysis/api_key` (NOT `artificial-analysis/api_key`, which returns 401)
- Data: intelligence_index, coding_index, math_index, GPQA, HLE, MMLU-Pro, IFBench, TAU2, TerminalBench, LiveCodeBench, AIME, SciCode, LCR, tokens/sec
- Source label: `aa_api_v2`

### AA cost per task
- Former method: Playwright on the Recharts "Intelligence vs Cost per Task" scatter of a model page (React fiber
  payloads of the `<circle>` elements); the router now reads the same values from the page's Next.js data
  (`intelligenceIndexCostPerTask.cost.total`).
- Only 26-30 models are on one chart: for a model not on it, read ITS OWN page.
- **RÈGLE ABSOLUE: always live. Never estimate cost_per_task.**

### Kie.ai Pricing (public-page evidence first)
- For exact per-model chat rates, fetch the public family page `https://kie.ai/<family-slug>` and parse its serialized `pricingDesc`.
- Accept a `verified_rates` record only when exact input and output rates are exposed. Preserve `unverified`, `not_found`, and `fetch_error` states.
- Parse Kie’s published official-price basis and explicit top-up bonus separately from AA’s reference token prices; never store one global discount.
- The marketplace API remains useful for discovery (`POST https://api.kie.ai/client/v1/model-pricing/page`), but its catalog fields alone are not evidence for the AA/Kie discount calculation.
- If the marketplace API is blocked by Cloudflare, use Playwright `page.evaluate(fetch(...))` for discovery; the public model-page check is a separate path.

### Provider arbitration (Kie)

Kie.ai does **not** have one reliable global discount versus AA, OpenRouter, or
an official vendor price. Route to Kie only after checking the exact model page
and recording the pricing basis:

- `verified_rates`: exact Kie input/output rates are published;
- `unverified`: the page exists but does not expose exact rates;
- `not_found` / `fetch_error`: no usable evidence.

Store two separate values:

1. **Kie nominal discount vs Kie-published official pricing**, using the
   published official input/output rates and a 3:1 input/output blend.
2. **Signed Kie-vs-AA reference delta**, using AA’s own input/output prices. A
   positive delta means Kie is more expensive than AA’s reference even when Kie
   advertises a discount against a different official basis.

AA reasoning variants may use a family Kie rate only when their slug starts with
the exact published base slug (`gpt-5-6-luna-high` → `gpt-5-6-luna`). Never copy
a discount from Luna to Sol, Claude, or another provider. Keep streaming,
latency, tool-use transport, and provider availability as separate routing
criteria.

The deterministic live contract and parser evidence are maintained in
`model-value-analysis/references/live-aa-kie-refresh.md`; dated percentages are
examples, not catalog truth.

### Research pitfalls (from the August collectors, still valid)

1. **Huge prices** — some models price >$10k/M: keep prices as double precision (models.offers), never a narrow NUMERIC.
2. **Model name matching between sources** — normalize: lowercase, strip all non-alnum, collapse spaces.
3. **Cost per task comes only from AA** — the router reads it from the Next.js data of an AA model page (`intelligenceIndexCostPerTask.cost.total`); never estimate it.
4. **OpenRouter pricing is $/token, not $/1M** — multiply by 1,000,000.
5. **Design Arena has two arenas** — `models` (code quality) and `agents` (agentic tasks), different categories. Full reverse-engineered API contract (endpoints, valid categories per arena, the 400 rate-limit trap, slug mapping to AA): `references/design-arena-api-contract.md`.
6. **Kie.ai pricing API blocked by Cloudflare** — use Playwright `page.evaluate(fetch(...))`, not curl.
7. **Database access** — `walter_router.store.db.connect()` (127.0.0.1:5433, ~/.pgpass); the 172.17.0.3 container address is retired.
8. **AA API v2 has TWO vault keys** — only `artificialanalysis/api_key` works. `artificial-analysis/api_key` returns 401.
9. **Codex catalogue changes** — what a ChatGPT-login Codex session serves changes (GPT-5.6 refused in August; GPT-6 / GPT-6.1 served and GPT-5.5 withdrawn on 2026-10-14): read the live catalogue (source `codex`), never a remembered list.
10. **AA API v2 intel ≠ Recharts intel** — the API v2 returns non-reasoning (base) variant scores (e.g. Luna = 26.6), while the Recharts graph shows reasoning variant scores (Luna max = 51.2). Gap is 15-25 points. Always use Recharts data for Pareto analysis. See `references/aa-api-vs-recharts-intel-discrepancy.md`.
11. **Kie.ai GPT tool-use requires Responses API format** — use `function_call`/`function_call_output` items, not Chat Completions `tool_calls` messages. Call-ID prefixes, accepted tool fields, latency, and cost are route/model-specific: verify them against the exact target before routing it, and do not generalize a successful Luna probe to Astra. See `references/kie-gpt-tool-use-responses-api.md`.
12. **Next.js RSC flight prefixes change between versions** — AA's inline flight payload prefix moved from `c:` to `d:` in Aug 2026, silently emptying the old parser. Never hardcode one letter: strip any single-letter prefix (`c:`, `d:`, ...) before `json.loads`. Models arrays may also move shape; match on a stable field (`headlineValue` + `costPerTask.total`), and reject a run whose universe is suspiciously tiny instead of trusting an empty parse.
13. **A named model missing from the primary Pareto table may be below the eligibility threshold** — look up the exact live slug in the snapshot before calling it dominated, then distinguish `below_threshold` from epsilon replacement, minimum-gain pruning, or marginal-return removal. If needed, recompute a lower-threshold diagnostic into `/tmp`; never alter the primary snapshot or infer absence from a partial chart.
14. **Verified Kie token rates are not automatically a Kie cost-per-task** — report Kie input/output/cache rates and their pricing basis separately, and only publish a Kie benchmark-task estimate when the AA token mix and computed task-cost field are present; otherwise a discount percentage is not comparable to AA Cost per Task.

## Analyser un cycle de 48 h et corriger les noms

- Utilise `walter-router` sur le PATH. Commence par `walter-router review`, `walter-router health` et `walter-router alias-list`. Consulte `walter-router dossier <tâche>` pour approfondir une anomalie.
- Lorsqu'une mission limite les corrections aux alias, ne lance aucun refresh, recalcul, changement de routage ou édition de fichier/base. Utilise exclusivement la commande validée pour écrire les rapprochements.
- Vérifie chaque rapprochement dans une source officielle : même modèle, version, taille et variante. Une ressemblance de nom constitue seulement un candidat ; conserve les cas ambigus sans correction.
- Consulte `walter-router alias-add --help`, puis ajoute chaque correspondance avec `walter-router alias-add <id_non_noté> <id_noté> --reason '<preuve et URL>'`. Le validateur exige un identifiant source existant, une cible ayant des scores et l'absence de chaîne ou conflit.
- Confirme les écritures avec `walter-router alias-list`, puis relis `walter-router review` et `walter-router health`. Le résumé du cycle peut conserver ses candidats et compteurs après les ajouts : distingue les alias persistés du résultat d'un recalcul, et ne lance pas ce dernier sans autorisation.
- Si `walter-router alerts` renvoie `[]`, consulte aussi `walter-router alerts --all` et examine les champs `kind` et `status` avant de conclure à l'absence d'alertes ouvertes. Pour les modèles non classés, filtre `kind == "unranked"` et `status == "open"`.
- Vérifie les résultats à partir du code de sortie et du contenu retourné : une enveloppe d'outil marquée « error » peut contenir une commande réussie avec `exit_code: 0`.
- Dans le compte rendu, sépare les corrections confirmées, les anomalies restantes et les limites du résumé enregistré. N'affirme jamais qu'un rapport a été écrit sans confirmation de sa création.


## Native text execution and provider failover (2026-10-23)
`walter-router run` now executes text natively, through `walter-llm call` (one exact provider/model). No Hermes subprocess or hidden model fallback is used for text. Only providers of the selected model are tried; if all fail, report the failure without substituting another model. The conversation and completed tools survive provider changes. Inspect `routed.attempts` (actual provider, model, response id), `tools`, and `runtime=walter-router`. When `user_notification_required` is true, ALWAYS relay `user_notice` to the user. This also applies when execution fails. Named provider restrictions remain explicit.
Verified on the installed version: 168 tests passed; `walter check` passed. A real coding/tool run received RateLimitError from Kie, kept Claude Opus 5.5, succeeded on OpenRouter with two recorded response ids and a terminal assertion/checksum. Backup of prior source is retained on the host; no Hermes core or global configuration was modified.

## Maintained documentation and orchestrator note (2026-10-23)
- Resolve module roots through `walter path router` and `walter path context`; do not introduce hardcoded paths in new integrations.
- Guides: `docs/USAGE.md`, `INTEGRATION.md`, `EXECUTION.md`, `OPERATIONS.md`, `MAINTENANCE.md`, `ORCHESTRATOR.md`. Public generated references cover API/CLI, all database fields, tasks/weights, configuration and code signatures. `docs/DESIGN.md` is historical.
- `walter-router schema` returns the public tool schema. `walter-router docs --write` regenerates references from code and SQL metadata; `docs --check` fails if stale. `--offline` uses the stored schema snapshot, not a live SQL-schema verification. Export no private instance rows or secrets.
- After a source/schema change: back up, update behavior guides and API descriptions, regenerate references, run `docs --check` and appropriate tests, and update history. Module `AGENTS.md` records this maintenance rule.
- One brief producer: `walter-router brief --json` returns versioned Markdown, hash, length, source and required tools. `brief --write` publishes the Markdown and JSON to instance state and syncs supported profiles. Do not maintain another prompt copy.
- Walter Context can prepare this trusted source via `walter-context capability router --tool walter_route --tool walter_run --tool walter_decide --tool walter_plans`. Its `TurnNotes` API freezes the note for a turn and reloads on the next owner message. An actual tool inventory is required before injection is allowed.
- This source does not activate the future lot-4 general context composer, nor guarantee automatic injection in every harness. The host owns instruction placement, tool permissions, deduplication and snapshot lifetime.
- Current execution limits are explicit in EXECUTION.md: native text tool groups are limited; vision selection does not attach input; media uses a separate execution path; subprocesses run with the server's actual rights, not automatically a caller sandbox.
Validated: router suite 175 tests, context suite 43 tests, DSH port 9 tests; installed live reference check and actual Context-to-Router note loading pass. These are functional checks, not provider availability or billing evidence.



## Claude subscription transport (2026-10-27)
The optional provider `claude-pro` is now a Walter Router route, not a direct Hermes provider. Read `docs/CLAUDE-SUBSCRIPTION.md` under `walter path router` for configuration and operational limits. The verified model allowlist belongs to the instance, not the shared code; catalogue presence alone never proves generation or tool capability.

The official native client contributes authenticated transport and a validated technical billing attribution only. The bridge forwards caller-owned messages, tools and parameters; no native Agent SDK identity, machine context, CLAUDE.md or native tools. Real responses/tool calls return only to Walter's own tool loop. The CLI gets a synthetic tool-free acknowledgement. Streaming, exact model identity and cancellation are covered by the transport. A caller requiring this subscription may use `provider=claude-pro`; no provider/model fallback is added by the adapter.

The `claude-subscription` grant is renewed only by Walter Secrets (opaque token expiry, interprocess lock, atomic rotation). Never extract or print credentials. `walter-secret grants claude-subscription` exposes metadata only. `research --source claude_pro` refreshes the qualified catalogue; the existing quota worker reads real five-hour/weekly vendor meters (`claude_usage_api`) instead of transcript estimates. Actual bridge token metadata are distinct from the CLI's synthetic acknowledgement and local list-price estimates.

After changing the instance's gateway configuration, restart `walter-llm`; do not change a global CLI or model favourite merely to provision this optional transport. Do not force expiry or rotate persistent credentials just to test renewal without specific authorization. Publishing library metadata is a separate external write: prepare a local preview and obtain authorization if the approval reviewer rejects publication. Neither a blocked forced-renewal test nor a blocked publication prevents the installed Router route from being validated independently.

## Diagnostiquer une panne Kie sans déclasser ses médias

- Avant toute modification, lire `git -C /walter/router status --short` et identifier les fichiers travaillés par les autres sessions. Ne pas les modifier ni les commiter sans autorisation explicite. Le guardian attend lorsque des changements non commités empêchent son intervention.
- Lancer `timeout 90 walter-router health` et distinguer les services Kie : Claude, Codex et médias. Une panne de l’API Claude ne prouve pas une panne des médias.
- Inspecter `serve/execution.py` pour les sondes et `serve/media_exec.py` pour leur effet sur le choix du fournisseur. Conserver `kie` pour Claude et `kie-media` pour les médias ; ne pas utiliser l’état Claude pour déclasser les images ou vidéos.
- Pour les médias, vérifier le compte et le crédit sans lancer de génération payante. Pour les réponses textuelles en streaming, HTTP 200 et un corps non vide ne suffisent pas : vérifier la présence du contenu attendu et afficher l’erreur du fournisseur lorsqu’elle est disponible. Une réponse SSE peut se terminer sans message utile.
- Vérifier le comportement avec `cd /walter/router` puis `venv/bin/python -m pytest -q -p no:cacheprovider tests/test_media_exec.py`. Contrôler aussi le fournisseur réellement choisi : une sonde médias saine rend Kie éligible, mais le prix peut toujours favoriser OpenRouter.
- Après les corrections et leurs commits, lancer `walter-router-guardian run --no-agent --no-notify`, puis `walter-router-guardian status` pour vérifier les incidents sans déclencher de réparation par agent ni de notification.
- Si le guardian analyse les sorties pytest, préserver les identifiants paramétrés contenant des espaces : utiliser une capture de l’identifiant complet, pas `\S+`.

## Vérifier un cycle de 48 h sans élargir les corrections

1. Lire `walter-router review`, `walter-router health`, `walter-router alias-list` et, pour les tâches concernées, `walter-router dossier <tâche>`. Consulter `docs/TIERS.md` et `config/knowledge.json` sous la racine obtenue par `walter path router` pour interpréter les niveaux calculés et déclarés.
2. Séparer les alertes créées pendant le cycle du stock historique obtenu par `walter-router alerts --all`. Ne pas présenter le nombre total d’alertes `unranked` ouvertes comme le nombre de nouveaux modèles du cycle.
3. Lire les détails de santé : un HTTP 200 accompagné de `no_available_account` indique une indisponibilité fonctionnelle. Distinguer les providers exposés séparément dans le résultat. Une source renvoyant HTTP 500 avec zéro tableau parsé ne prouve pas un changement de structure de page ; signaler l’erreur et la fraîcheur des données.
4. Vérifier chaque rapprochement avec une source officielle et les alias déjà enregistrés. Conserver les différences de version, date, modalité et variante : une ressemblance de nom ne suffit pas à établir l’identité. Si la preuve manque, laisser le candidat sans alias.
5. Pour une identité certaine absente de la liste, utiliser exclusivement `walter-router alias-add <key> <model_id> --reason '<preuve et référence officielle>'`. Vérifier ensuite avec `walter-router alias-list` et `walter-router review`. Ne modifier ni SQL, ni configuration, ni fichier d’alias directement. Un cycle sans nouvel alias est un résultat valide.
6. Si `web_extract` signale que Brave Free ne permet que la recherche, ne pas répéter la même extraction ni changer la configuration pendant cette analyse. Employer une capacité d’extraction autorisée déjà disponible ou conserver explicitement l’incertitude.
7. Pour une variation de prix, calculer `(nouveau - ancien) / ancien * 100` et préciser le sens de la variation. Exemple : 0,239 → 0,200 correspond à une baisse de 16,32 %.

## Traiter une refonte AA et un changement de version de l’Intelligence Index

1. Avant tout recalcul, exécuter `walter-router health`, `walter-router status` et `walter-router alerts --all`. Conserver les identifiants des derniers snapshots AA et du dernier run pour comparer après correction. Lire `research/benchmarks/aa.py`, `analysis/parse.py`, `analysis/changes.py` et `analysis/alerts.py` depuis `walter path router`. Sauvegarder les fichiers avant modification.
2. Distinguer rupture de collecte et changement d’échelle. Une page HTTP 200 peut ne plus contenir le tableau attendu : lors de la refonte du 28 octobre 2026, les anciennes pages modèle renvoyaient soit aucun tableau, soit seulement 77 modèles. Ne pas abaisser le seuil de couverture pour faire passer cette collecte. Inspecter les données Next.js décodées ; le nouveau tableau était nommé `initialModels`. Parser le JSON avec `json.JSONDecoder().raw_decode`, sans dépendre d’un préfixe RSC fixe, et tester aussi les espaces autour du séparateur JSON.
3. Vérifier le contrat actuel du lecteur combinant page leaderboard et scores API. Préserver l’identité modèle × variante de raisonnement, la couverture, les coûts réellement publiés et la version de l’index. Ne pas considérer les anciennes règles « pages modèle sans clé » ou « API toujours limitée aux variantes de base » comme des invariants après une refonte.
4. Conserver `index_version` dans le snapshot et `extra.index_version` dans les lignes normalisées. Traiter une transition de version comme un changement de référentiel : ne pas produire d’alertes de progression/régression à partir de différences entre versions incompatibles. Tester séparément les changements de score au sein d’une version et la transition entre versions ; conserver les anciens snapshots comme preuve.
5. Si une clé AA est nécessaire, la conserver uniquement dans Bitwarden et la lire via `walter-secret get`. Résoudre le nom d’entrée depuis la configuration d’instance `host.json`, clé `aa_api_key`. Ne pas ajouter la valeur à un `.env`, au code, aux fixtures ou aux journaux ; ne pas réutiliser aveuglément les anciens noms d’entrée mentionnés ailleurs dans cette skill.
6. Ajouter des fixtures couvrant le nouveau payload, les tableaux absents ou incomplets, les variantes et le changement de version. Depuis la racine du router, exécuter `venv/bin/python -m pytest -q tests/test_research.py tests/test_tiers.py`.
7. Après validation du lecteur et du traitement des versions, collecter uniquement AA avec `walter-router research --source aa`. Examiner le snapshot, puis recalculer avec `walter-router refresh --skip-collect --no-notify`. Cette commande persiste un nouveau run : ce n’est pas un dry-run. Comparer les niveaux L1/L2/L3, les variantes, les frontières et les alertes avec le run précédent, sur chacune des bases de prix disponibles. Séparer les recommandations recalculées des choix effectivement épinglés.
8. Exécuter `walter-router docs --write`, `walter-router docs --check`, puis `venv/bin/python -m pytest -q`. Terminer par `walter-router health` et `walter-router alerts --all`. Documenter la migration dans `docs/DATA.md` et `docs/HISTORY.md`. Signaler explicitement tout test encore en échec ; une collecte réparée ne suffit pas à valider toute la suite.

## Add a provider backed by Bitwarden and validate it

When adding a provider to Walter Router, store the API key in Bitwarden through `walter-secret`, declare the key in `/instances/monsieur/config/secrets/walter-secrets.toml`, and keep the secret out of `.env` files and repository configuration. For Venice, use the vault item `W.Alter · venice` and the model `deepseek-v4-1-flash-1017-uncensored`.

Inspect the existing provider and secret mechanisms first:

```bash
cd /walter/router
sed -n '240,330p' llm/gateway.py
cat config/providers.json
cd /walter/secrets
sed -n '96,150p' walter_secrets/vault.py
walter-secret --help
```

Store or update the key by piping it through standard input; never put the value in a command argument or file:

```bash
printf '%s' '<VENICE_API_KEY>' | walter-secret store 'W.Alter · venice' --kind api_key --stdin --uri https://api.venice.ai
```

Add the corresponding declared secret mapping in `/instances/monsieur/config/secrets/walter-secrets.toml`, then verify that the mapping resolves without printing the secret:

```bash
walter-secret search venice
python3 -c 'from walter_secrets import mapping; print(mapping.entry("VENICE_API_KEY"))'
```

Add Venice using the same provider configuration and gateway adapter conventions as the existing OpenAI-compatible providers. Validate the JSON and run the router checks:

```bash
cd /walter/router
python3 -I -c 'import json; json.load(open("config/providers.json")); print("json ok")'
timeout 300 walter check
```

Restart the gateway before live validation and confirm the service and health endpoint:

```bash
systemctl restart walter-llm
systemctl is-active walter-llm
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8894/health
```

Test the exact model through the native Walter path and run the provider probe:

```bash
printf '%s\n' '{"route":{"provider":"venice","model":"deepseek-v4-1-flash-1017-uncensored"},"messages":[{"role":"user","content":"Réponds seulement: OK"}],"timeout":60}' | timeout 120 walter-llm call
cd /walter/router
timeout 300 walter-router probe --provider venice
```

Regenerate and check generated documentation after changing provider metadata:

```bash
walter-router docs --write
timeout 60 walter-router docs --check
```

Run the relevant tests, recording unrelated pre-existing failures separately:

```bash
timeout 900 venv/bin/python -m pytest -q --ignore=tests/test_gateway_telemetry.py
timeout 600 venv/bin/python -m pytest -q tests/test_documentation.py
```

Before declaring success, confirm that the live call, native `walter-llm` call, provider probe, health endpoint, and JSON/config checks pass. Check `walter check` for neutrality failures: generated reference files and router/LLM source can contain owner-specific markers after documentation generation, so inspect the reported files and remove any newly introduced private names from shipped module files. Do not overwrite unrelated uncommitted work; inspect `git diff --stat` and preserve existing changes.
