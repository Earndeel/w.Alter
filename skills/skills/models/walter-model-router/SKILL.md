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

## Further reading (moved out of this file on 2026-11-01, unchanged)

- `references/research-sources-and-pitfalls.md` — Research reference: every leaderboard / price source and its pitfalls (still valid).
- `references/operations-48h-cycle.md` — Analysing, verifying and reviewing a 48-hour refresh cycle, fixing names with alias-only authority, handling an AA redesign or Intelligence Index version change.
- `references/providers-and-transport.md` — Native text execution and provider failover, the Claude subscription transport, diagnosing a Kie outage without downgrading its media, adding a Bitwarden-backed provider.
- `references/documentation-and-orchestrator.md` — Which documentation is maintained, and the orchestrator note (2026-10-23).

## Review a deterministic 48-hour cycle under alias-only authorization

- Read `walter-router review` and `walter-router health`; correlate the run ID, source errors and snapshot ages before interpreting rankings. Report stale or failed sources as limits on the analysis; do not repair collectors during an alias-only review.
- Read `walter-router docs` and `walter-router --help` to discover current documentation and commands. Use `walter-router dossier <task>` for task-specific evidence and `walter-router alias-list` for existing mappings.
- Treat `/opt/walter-router/walter_router/aliases.json` as a legacy location: it was absent in this session; the file was found at `/opt/walter-router/analysis/aliases.json`. Resolve the module root with `walter path router` and verify the current layout before reading implementation files. Never edit the alias file directly.
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
with psycopg.connect('host=127.0.0.1 port=5433 dbname=hindsight user=hindsight') as c:
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
