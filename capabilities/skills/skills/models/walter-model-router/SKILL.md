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

Module `/walter/cognition/router` (also reachable as `/walter/cognition/router`), command `walter-router` on the PATH. Data: schema
`models` in PostgreSQL 127.0.0.1:5433 db `walter` (password only in ~/.pgpass; every table and view is commented).
Read first: `/walter/cognition/router/README.md` (current state: layout, how a choice is made, consumers, access, rules), then
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
- `walter-router health`, `status`, `review`, `alerts --all`; tests `cd /walter/cognition/router && venv/bin/python -m pytest -q`.
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

## Further reading (moved out of this file on 2026-11-01, unchanged)

- `references/research-sources-and-pitfalls.md` — Research reference: every leaderboard / price source and its pitfalls (still valid).
- `references/operations-48h-cycle.md` — Analysing, verifying and reviewing a 48-hour refresh cycle, fixing names with alias-only authority, handling an AA redesign or Intelligence Index version change.
- `references/providers-and-transport.md` — Native text execution and provider failover, the Claude subscription transport, diagnosing a Kie outage without downgrading its media, adding a Bitwarden-backed provider.
- `references/documentation-and-orchestrator.md` — Which documentation is maintained, and the orchestrator note (2026-10-23).

## Review a deterministic 48-hour cycle under alias-only authorization

- Read `walter-router review` and `walter-router health`; correlate the run ID, source errors and snapshot ages before interpreting rankings. Report stale or failed sources as limits on the analysis; do not repair collectors during an alias-only review.
- Read `walter-router docs` and `walter-router --help` to discover current documentation and commands. Use `walter-router dossier <task>` for task-specific evidence and `walter-router alias-list` for existing mappings.
- Treat `/walter/cognition/router/walter_router/aliases.json` as a legacy location: it was absent in this session; the file was found at `/walter/cognition/router/analysis/aliases.json`. Resolve the module root with `walter path router` and verify the current layout before reading implementation files. Never edit the alias file directly.
- Treat unmatched-name candidates as investigation leads, not established equivalences. Verify identity using primary provider documentation; similar names, shared parameter counts, date suffixes, experimental variants and specialist suffixes do not establish equivalence.
- Before an authorized correction, inspect `walter-router alias-add --help` for the exact current syntax. Apply only verified equivalences through `alias-add`, then check `alias-list` and rerun `review` to verify the result. If evidence is insufficient, leave the candidate unresolved.
- Keep the authorization boundary explicit: an alias-only analysis permits no direct database writes, configuration changes, collector repairs, model switches or report-file creation unless separately authorized. Return the analysis in the response when file writes are excluded.

## Vérifier et maintenir la voie Antigravity de Google AI Pro

- Utiliser la CLI officielle `agy` et l'adaptateur existant ; consulter `docs/ANTIGRAVITY-SUBSCRIPTION.md` et `llm/antigravity_subscription.py` dans le module retourné par `walter path router` avant toute modification. Ne pas déduire l'accès Antigravity de l'installation ou de l'authentification de Gemini CLI.
- Sur l'instance de Monsieur, interroger le catalogue avec le HOME dédié à l'abonnement :
  ```bash
  A=/user/Lucas/state/router/antigravity
  (cd "$A/home" && HOME="$A/home" timeout 60 "$A/bin/agy" models </dev/null)
  ```
  Conserver le code de sortie et les erreurs : une authentification expirée ne signifie pas que le catalogue est vide. Ne jamais afficher les fichiers d'identifiants.
- Distinguer les variantes de réflexion des modèles distincts. Vérifier les identifiants publiés par la CLI et leur correspondance dans l'adaptateur : le catalogue observé utilisait notamment `gemini-3.8-flash`, tandis que d'autres couches employaient `gemini-3-8-flash`.
- Le cycle de collecte de 48 h découvre les modèles ; cette découverte ne prouve pas qu'ils fonctionnent et ne les autorise pas automatiquement. Avant d'étendre la liste des modèles vérifiés, effectuer un appel réel via le gateway, puis vérifier les capacités annoncées : plusieurs tours, streaming et JSON si elles doivent être exposées.
- Pour tester une route précise, utiliser la sous-commande `call`, et non `exact` :
  ```bash
  ROUTER_ROOT=$(walter path router)
  printf '%s\n' '{"route":{"provider":"antigravity","model":"gemini-3.8-flash","reasoning":"low","access":"subscription"},"messages":[{"role":"user","content":"Dis bonjour en trois mots."}],"timeout":120}' | "$ROUTER_ROOT/llm/gateway.py" call
  ```
  Examiner la réponse complète, son champ `ok`, le modèle retourné et le code de sortie. Une réponse textuelle réussie ne suffit pas à valider le streaming ni les outils. La voie installée sert du texte, avec les outils CLI désactivés.
- Vérifier séparément l'offre d'abonnement et le choix des tâches : une offre disponible et prioritaire ne signifie pas qu'une tâche la sélectionne. Ne pas changer les modèles des tâches simplement parce qu'un modèle devient disponible dans l'abonnement.
- Après modification du routeur, régénérer sa référence avec `walter-router docs --write`, puis exécuter les tests concernés. La session a rencontré des environnements Python distincts : LiteLLM était absent du Python de test et pytest absent du venv LLM ; un échec d'import doit être distingué d'une régression de l'adaptateur. Vérifier ensuite `systemctl is-active walter-llm` et `curl -fsS http://127.0.0.1:8894/health` si le service a été redémarré.

## Auditer les appels Codex et retrouver les entrées/sorties mémoire

1. Interroger `models.exec_log` en lecture seule avec `walter-python` et le compte PostgreSQL `hindsight`. Le compte `postgres` ne correspondait pas à l’authentification disponible dans cette session. Laisser libpq utiliser `/root/.pgpass` sans afficher son contenu.

```bash
walter-python - <<'PY'
import psycopg
from datetime import datetime, timezone, timedelta
end = datetime.now(timezone.utc)
start = end - timedelta(hours=48)
with psycopg.connect('host=127.0.0.1 port=5433 dbname=walter user=walter') as c:
    c.execute('SET TRANSACTION READ ONLY')
    print('Fenêtre UTC :', start.isoformat(), end.isoformat())
    rows = c.execute('''
        SELECT exec_id, at, task, role, model, ok, skipped,
               seconds, usage, run_id
        FROM models.exec_log
        WHERE provider = 'codex' AND at >= %s AND at < %s
        ORDER BY at, exec_id
    ''', (start, end)).fetchall()
    for row in rows:
        print(row)
PY
```

2. Fixer une seule fenêtre `[start, end)` pour toutes les requêtes du rapport. Préciser le fuseau affiché et distinguer 48 heures glissantes de deux jours calendaires. Pour l’extraction mémoire, filtrer `task='memory_extraction'`, puis regrouper par `role`, `model`, `ok` et `skipped`. Les compteurs de jetons observés sont `usage->>'in'` et `usage->>'out'`. Distinguer les fiches de sujets de Walter Memory du compilateur de profil, qui partagent ce poste.

3. Vérifier le routage actuel avec `walter-router pick memory_extraction`. Rapporter séparément le modèle historique enregistré dans `exec_log` et le niveau de raisonnement actuellement configuré. Ne pas attribuer rétroactivement ce niveau à chaque appel si aucune trace historique ne le conserve.

4. Pour les fiches de sujets, lire le code `walter_memory/views.py` du module Memory, notamment `CARD_PROMPT` et la construction des messages. Inspecter le schéma de `views.version`, puis consulter `built_at`, `view_key`, `content` et `source_refs` avec `depth='overview'`. Les références permettent de retrouver les échanges via `logs_timeline` et `logs_get`. Chercher également la version précédente de la fiche lorsque l’entrée la comprend.

5. Distinguer la sortie persistée dans une fiche, une entrée reconstruite depuis le code et les échanges, et une requête/réponse brute effectivement journalisée. Une proximité entre `exec_log.at` et `views.version.built_at` ne prouve pas une correspondance : plusieurs opérations peuvent se suivre à quelques secondes d’intervalle. Marquer ces rapprochements comme probables et signaler les appels sans résultat attribuable.

6. Pour les appels Guardians, distinguer le superviseur général `walter-guardians` du Guardian du routeur. Consulter `walter-guardians status` et l’état du Guardian concerné ; ne pas supposer que `models.guardian_incidents` contient les incidents du superviseur général. Un verdict conservé ne constitue pas la réponse JSON brute complète.

7. Présenter tous les appels de la fenêtre demandée, les agrégats et les limites de reconstruction. Ne jamais promettre les inputs/outputs exacts lorsque seuls les métadonnées, les fiches dérivées ou les verdicts ont été conservés.

## Analyser un cycle de 48 h et corriger les alias
- Respecter le périmètre du cycle : si seule la commande `alias-add` est autorisée en écriture, ne modifier ni fichiers, ni configuration, ni base ; ne pas enregistrer de rapport sur disque.
- Lire `walter-router review`, `walter-router health` et `walter-router alias-list`. Distinguer les erreurs de collecte, la fraîcheur des sources, les problèmes de providers et les candidats de rapprochement de noms. Une source périmée ne prouve pas une régression du modèle.
- Pour interpréter les résultats, consulter `walter-router dossier <tâche>` et les documents `docs/TIERS.md` et `config/knowledge.json` du module, dont la racine se résout avec `walter path router`.
- Utiliser `walter-router alias-list` pour lire les alias : le chemin historique `walter_router/aliases.json` peut ne plus exister. Ne pas recréer ce fichier.
- Avant tout rapprochement, vérifier auprès d'une source officielle que les deux identifiants désignent exactement la même version du modèle. Une famille, un nom commercial proche ou une nouvelle génération ne suffisent pas. Laisser les cas ambigus inchangés.
- Appliquer uniquement les correspondances établies avec `walter-router alias-add <alias-source> <model_id-canonique> --reason '<preuve précise et URL officielle>'`. Vérifier le sens de la correspondance dans la liste existante.
- Relire `walter-router alias-list` après chaque ajout. Examiner le code de sortie et le JSON : l'enveloppe d'un outil peut afficher « error » alors que la commande a terminé avec le code 0 et renvoyé `added` et `model_id`.
- Pour examiner les alertes historiques et le catalogue, utiliser `walter-router alerts --all` et `walter-router library --json`. Rapporter les anomalies restantes sans tenter de réparer les collecteurs lorsque cette réparation sort du périmètre autorisé.

## Rafraîchir et vérifier le poste rerank

- Résoudre le module avec `walter path router`, puis travailler dans ce répertoire. Capturer `walter-router dossier rerank` avant toute relance pour comparer classement, mesures, offres et rôle choisi.
- Relancer Agentset avec `walter-router research --source agentset`. Attention : le filtre porte sur une source, pas sur un poste ; Agentset couvre aussi les embeddings. Ne pas présenter `--analyse` comme une analyse limitée au rerank sans vérifier sa portée.
- Vérifier la date du leaderboard et les modèles réellement mesurés. Un snapshot inchangé prouve seulement que la collecte n'a pas changé ; il ne prouve pas que les modèles récents sont évalués. Distinguer les modèles disponibles chez un fournisseur des modèles disposant d'un benchmark indépendant.
- Pour contrôler les offres OpenRouter, consulter `https://openrouter.ai/api/v1/models?output_modalities=all` et filtrer les modèles dont `architecture.output_modalities` contient `rerank`, ainsi que les identifiants contenant `rerank`. Comparer le tarif API à la page officielle : un champ `pricing.prompt` à zéro ne suffit pas à conclure à la gratuité. Lors de cette session, des offres récentes avaient un prix par token publié sur leur page alors que l'API renvoyait zéro.
- Préserver les unités : ne pas assimiler un prix par recherche à un prix par million de tokens d'entrée. Si une correction est nécessaire, sauvegarder les fichiers puis vérifier la chaîne complète : collecte dans `research/prices/openrouter.py`, conversion dans `analysis/parse.py`, offres stockées, récupération et affichage dans `analysis/catalog.py`. Corriger seulement le parseur ne suffit pas : le catalogue récupérait le prix d'entrée uniquement pour les modèles de décision et continuait d'afficher « prix non publié » pour le rerank.
- Après correction, exécuter `walter-python -m pytest -q tests/test_service_boards.py tests/test_router.py`, puis `walter-router research --source openrouter --analyse`. Contrôler `walter-router pick rerank` et `walter-router dossier rerank`, notamment le fournisseur, l'identifiant du modèle et l'unité du prix affiché.
- Exécuter la suite `walter-python -m pytest -q tests`. Si `tests/test_documentation.py` signale une référence générée périmée, lancer `walter-router docs --write`, examiner le diff et relancer les tests. Contrôler aussi `walter-router health` ; distinguer les sources anciennes sans rapport avec le rerank des erreurs introduites.
- Après un changement de modèle autorisé par Monsieur, vérifier le consommateur réel avec `walter_memory.search.search("Walter Router choix du modèle de reranking", limit=8, rerank=True, max_privacy="redacted_cloud")`. Ne sortir que le nombre de résultats et la durée. Vérifier ensuite les métadonnées de l'appel dans `system.model_calls` avec `SELECT model, status, cost_usd, at FROM system.model_calls WHERE processor='search.rerank' ORDER BY at DESC LIMIT 4`. La connexion mémoire renvoie des lignes dictionnaires ; la colonne temporelle s'appelle `at`, pas `created_at`. Relier la vérification à l'heure du test sans afficher les résultats personnels.
- Ne pas transformer un petit test de pertinence ou une baisse de coût en preuve de supériorité générale. Consigner séparément l'autorisation du changement, les benchmarks disponibles et les observations du test réel.

## Vérifier un cycle de 48 h sans modifier le routeur

- Si la collecte et le calcul sont déjà faits, ne les relancez pas. Commencez par les commandes de lecture :
  ```sh
  date -u +%Y%m%d
  /walter/cognition/router/bin/walter-router review
  /walter/cognition/router/bin/walter-router health
  /walter/cognition/router/bin/walter-router alias-list
  ```
- Consultez la méthode dans `/walter/cognition/router/docs/TIERS.md` et les préférences dans `/walter/cognition/router/config/knowledge.json`. Pour approfondir une tâche, utilisez `/walter/cognition/router/bin/walter-router dossier <tâche>` ; ne recalculez pas arbitrairement les niveaux.
- Pour les alias, privilégiez `alias-list`. Le chemin `/walter/cognition/router/walter_router/aliases.json` peut être absent : dans la session observée, le fichier était situé à `/walter/cognition/router/analysis/aliases.json`. Lisez ce fichier si nécessaire, sans le modifier.
- Avant toute correction de nom, consultez `/walter/cognition/router/bin/walter-router --help`, puis l'aide d'`alias-add` pour obtenir la syntaxe effective. Vérifiez que les deux noms désignent bien le même modèle et la même variante ; un rapprochement proposé n'est pas une preuve. Utilisez uniquement la commande validée `alias-add`, jamais une écriture directe dans la base, les alias ou la configuration. Relisez ensuite `alias-list` et `review` pour vérifier le résultat.
- Distinguez la réussite globale du cycle de la fraîcheur de chaque source : un cycle `ok` peut coexister avec une erreur de collecte et des scores périmés. Signalez l'âge, le périmètre touché et l'erreur exacte ; présentez une cause supposée comme une hypothèse. Ne réparez pas le collecteur pendant une mission limitée à l'analyse et aux alias.
- Ne déléguez pas et n'appelez pas d'autres modèles lorsque le mandat l'interdit. Ne modifiez aucun autre fichier du projet.

## Audit Preflight production routing and Router context delivery

When asked whether a Router change is live, verify the active call path, actual root-run routing, and context delivery separately. Do not treat implemented functions, tests, documentation, or available MCP tools as proof of deployment. Keep this audit read-only unless Monsieur authorizes changes.

### 1. Locate the active Preflight question selector

```bash
cd /walter/cognition/context
grep -rn -E 'def questions_v3|def questions_v2|def questions\b|questions_v3\(|questions\(req' --include='*.py' walter_context
sed -n '230,300p' walter_context/preflight/__init__.py
```

Trace callers, not just definitions. In this session, the new question set existed, but the production path still used the old task-family question near line 278. Recheck the current location rather than assuming this line number remains valid.

### 2. Verify what actually served recent turns

Use the installed Hindsight PostgreSQL container. A guessed `postgres` role failed in this setup. Read only the username from the existing client configuration; never print the full `.pgpass` or its password field.

```bash
U=$(cut -d: -f4 /root/.pgpass | head -1)
Q(){ docker exec -i walter-pg psql -U "$U" -d walter "$@"; }
Q -At -c "select column_name || ' ' || data_type from information_schema.columns where table_schema='runs' and table_name='runs'"
Q -c "select origin->>'runtime' runtime, routing->>'applied' applied, routing->'requested'->>'task' task, routing->'requested'->>'level' level, count(*) from runs.runs where started_at > now()-interval '3 days' and parent_run_id is null group by 1,2,3,4 order by 1,5 desc"
Q -At -c "select started_at, origin->>'runtime', routing::text from runs.runs where parent_run_id is null and routing->>'applied'='true' order by started_at desc limit 4"
```

Use `started_at`, not an assumed `created_at`. Exclude child runs with `parent_run_id is null` when auditing the main model; specialist delegation is a separate behavior. Distinguish a requested task family from an applied route, and inspect full routing records to establish the served model. Separate runtimes before drawing production conclusions.

### 3. Trace Router knowledge into the model's context

```bash
walter-router brief --json
walter present notes --form m0
walter present notes --form m0 --m1 router
cd /walter/cognition/context
grep -n -E 'capabilities|tool_cards|injected|stable_capabilities' walter_context/retrieval.py
sed -n '1,150p' walter_context/capabilities.py
cat /user/Lucas/config/context/inject.json
cd /walter/core
grep -n -E 'def router_brief|def module_layer|def apply_toolset|def client_profile' walter_capabilities.py
cat config/toolsets.toml
grep -n -E 'capabilities|tool_cards|stable_capabilities' /opt/walter-core/hooks/walter_hook.py /opt/walter-core/server.py
```

Compare the short m0 note with the requested Router m1 usage guide. Trace retrieval selection, injection gating, and the runtime hook/server consumer. A brief generator or exposed `module_layer`/`router_brief` function does not prove the engine receives that content automatically. Check the relevant client toolset rather than assuming every runtime exposes the same interface.

### 4. Report distinct findings

State separately: which question set is called, whether recent main turns were actually rerouted, whether the short Router description is injected, and whether the full usage guide is injected or merely retrievable. Identify pending deployment gates without silently changing them. Explicitly state whether anything was modified.

## Audit the live Router cycle, agent launches, and recommendation inputs

1. Separate scheduled checks from actual model calls. Run `systemctl list-timers --all 'walter-router*'`, `systemctl cat walter-router-refresh.timer walter-router-guardian.timer walter-router-refresh.service`, and `journalctl -u walter-router-refresh.service --since '14 days ago' -o short-iso --no-pager`. Read the live timer definitions rather than assuming the 48 h refresh and 6 h guardian schedules are unchanged. From `cd /walter/cognition/router`, trace the cycle in `bin/walter-router-cycle`, the guardian checks in `guardian/checks.py`, and the conditional agent launches in `guardian/run.py` and `guardian/advice.py`. Do not count a guardian pass as an L3 call; it performs ordinary checks and only launches repair under its configured conditions.

2. Count actual Router missions from the Engine run table. The VM may not have host `psql`; use the container client without reading or printing `/etc/walter/database.url`:

```sh
docker exec walter-pg psql -U walter -d walter -Atc "SELECT started_at, origin->>'request_id', level, status, round(extract(epoch FROM ended_at-started_at)/60, 1) AS minutes, routing->'requested'->>'level' AS requested_level, routing->>'applied' AS override_applied FROM runs.runs WHERE started_at > now()-interval '14 days' AND origin->>'request_id' ILIKE '%router%' ORDER BY started_at;"
```

Group by mission type from the request ID. Report Engine run `level`, requested routing level, and whether the override applied separately; an L4 run with a requested L1 and `applied=false` is not evidence that L1 served it. Use `models.runs` for refresh-cycle status, not for agent launch counts:

```sh
docker exec walter-pg psql -U walter -d walter -Atc "SELECT run_id, status, started_at, finished_at FROM models.runs ORDER BY run_id DESC LIMIT 6;"
```

3. Check which model data was refreshed and how complete it is before claiming the Router knows a feature:

```sh
docker exec walter-pg psql -U walter -d walter -Atc "SELECT kind, fetched_at, row_count FROM models.latest_snapshots ORDER BY kind; SELECT count(*) AS total, count(context_length) AS with_context FROM models.catalog; SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema='models' AND table_name IN ('catalog','canonical','offers','endpoints') ORDER BY table_name, ordinal_position;"
```

Trace source definitions in `research/sources.py` and field normalization in `analysis/parse.py` and `analysis/ingest.py`. Check offer `modes`, `interface`, and `pricing` against the corresponding latest `snapshot_id`, not historical rows. For a cross-source naming mismatch, trace the source names through canonical records to the current provider offer before attributing a price or capability to the model. Treat missing metadata as unknown, not as unsupported or equivalent across providers.

4. Verify that collected data actually affects recommendations. Read `guardian/advice-brief.md` and `guardian/advice.py`, inspect the card builder in `analysis/catalog.py`, and run `bin/walter-router decision-needs` from the Router directory. Compare what the decision modules need with what the challenger-selection code checks and what the latest `analysis-run-*.json` under `/user/Lucas/logs/walter-router/` records. A requirement listed by `decision-needs` is not proof it gates a proposal. Likewise, distinguish scheduled source ingestion from outside research: compare the advice brief with `plan/news.py` before claiming that web research for subscription plans also discovers new models or benchmarks. Keep this audit read-only; do not trigger a refresh or change a poste just to verify it.

## Valider et déployer un changement de cache du payload

1. Sépare le texte système stable entre sessions (Soul, skills, présentations des modules) du texte propre à la session. Pour Claude, place le marqueur à la fin du bloc stable, pas à la fin d'un appel ponctuel. Pour OpenAI/Codex, retire les marqueurs et recolle les blocs : compare le texte envoyé avant/après au caractère près, séparateurs compris. Vérifie hors ligne que la route Claude via OpenRouter conserve les marqueurs ; ne dépense pas de crédit juste pour vérifier la sérialisation. Identifie et documente l'interrupteur de retour arrière avant l'activation. Exemple de dossier de reprise : `/user/Lucas/backups/changes/2026-11-24-payload-cache-deux-fournisseurs/README.md`.
2. Compare les mêmes cas avant/après, sans régénérer les réponses si seul le jugement doit être corrigé. Pour un cas sensible à la date ou à l'heure, donne au juge le même contexte horaire local de Monsieur pour toutes les variantes. Lis les `judge.jsonl` sous `/user/Lucas/state/core/engine/bench/payload/` : rapproche les lignes par `key`, vérifie la couverture et les scores invalides avant de comparer les moyennes, puis inspecte les régressions par cas. Des moyennes proches ne prouvent pas qu'aucune réponse individuelle n'a régressé.
3. Attends la fin des bancs et un créneau sans tour actif. Recoupe `pgrep -af '[p]ayload_bench'`, `find /user/Lucas/state/core/engine/native/sessions -name '*.jsonl' -mmin -5` et les dernières lignes de `/user/Lucas/logs/walter-llm.jsonl` ; l'absence de fichier récent n'est pas une preuve à elle seule. Redémarre d'abord `systemctl restart walter-llm`. Attends que `systemctl is-active walter-llm` confirme `active` et que `curl -fsS --max-time 3 http://127.0.0.1:8894/health` réussisse. Revérifie l'activité avant `systemctl restart walter-engine`, puis contrôle `systemctl is-active walter-engine` et `curl -fsS --max-time 3 http://127.0.0.1:8895/health`. En cas de traceback, relève le nouveau PID avec `systemctl show walter-engine -p MainPID --value` et lis `journalctl -u walter-engine --since '-2 min' --no-pager` : distingue les annulations de connexions de l'ancien processus des erreurs du nouveau.
4. Vérifie le budget avec `walter-llm test-budget`, puis lance un essai borné sur le compte de test, avec un libellé inédit : `cd /walter/core/engine && timeout 300 walter-python bench/payload_bench.py run --label cache-smoke-YYYYMMDD-HHMM --passes 1 --only f1_salut,f1_merci,f1_calcul --max-eur 0.05 --note 'post-restart cache smoke'`. Garde le code de sortie : ne masque pas un échec derrière `| tail` sans `pipefail`. Si le banc produit `turns.jsonl`, relève `status`, `models`, `first_prompt` et `first_cached`. Si le fichier manque, vérifie la sortie du banc et recoupe ses horaires avec `/user/Lucas/logs/walter-llm.jsonl` (`at`, `agent`, `provider`, `ok`, `usage`) avant de conclure. Mesure les premiers appels de sessions distinctes, pas seulement les tours suivants d'une session déjà chaude. Consigne séparément les mesures faites sur le service redémarré, les essais en processus séparé et les vérifications hors ligne. Un succès Codex ne valide pas Claude ; sans nouvel appel Claude, laisse sa confirmation en production ouverte.
