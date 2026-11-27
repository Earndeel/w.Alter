# core/interfaces/api — Engine API

| | |
|---|---|
| **Rôle** | La porte canonique du moteur Walter (lot E4) : toute interface — Telegram, web, modules Walter (one-shots du Router), tests et scénarios V1 — ouvre ou retrouve une conversation, soumet un message, suit son déroulé, lit le résultat d'un tour, l'interrompt et répond aux approbations par elle. |
| **Propriétaire** | walter-core (moteur). |
| **État** | Implémentée et prouvée le 10/11/2026 sur un hôte de test (7 contrôles de bout en bout, redémarrage compris ; délégation E5 : 6 contrôles, `scenarios/v1/engine_e5.py`). **En service, servie par le moteur natif** (`walter-engine`, `walter_engine/server.py` + `api.py`, `127.0.0.1:8895`, depuis le 17/11/2026, sans interrupteur). `[dsh.engine] api` ne concernait que DSH (désinstallé le 18/11). |
| **Ne fait pas** | Pas de second système de sessions, de runs ou de bus : sessions du noyau (`sessionController`), Run Plane et bus ouverts par les greffons `intake`/`events` pour chaque tour quelle que soit la porte. Ne décide d'aucune permission : elle publie la porte de la session à la politique unique (`core/security`). Jamais hors loopback. |
| **Contrats** | `../../engine/contracts/engine-api.v1.json` (opérations) ; événements client ci-dessous (vocabulaire de `engine-event.v1`). |

## Transport

- `POST /v1` avec l'enveloppe `{version: 1, op, …}` ; `GET /v1/health` ; `GET /v1/events?session_id=…[&since_seq=N]` (SSE).
- `127.0.0.1:8895` (production) ; jeton d'agent dans l'en-tête `Authorization: Bearer …`, jamais dans l'URL. Le jeton
  est créé une fois (0600) dans `@instance/bootstrap/engine/api.token` ; les clients le lisent là.
- Hébergée par le processus durable du moteur (`walter-engine`), jamais par une exécution headless.

## Opérations

| op | Effet |
|---|---|
| `session.open` | `{interface, conversation, principal{kind,id}, mode interactive\|command, permissions?, continue_session?, level?}` → `session_id = <porte>/<compte>/<conversation>`. Première fois : une session du noyau est créée ; ensuite (même après redémarrage) : la même (`resumed: true`). `continue_session: "dsh/vm/<id>"` (propriétaire seulement) rattache une session existante, par exemple commencée sur le web. `level: L1\|L2\|L3` (propriétaire seulement) épingle un niveau de texte du Router sur la conversation, aussi à une réouverture : chacun de ses runs le porte (`routing.requested.pinned_level`), walter-llm l'applique à la place du niveau jugé par le préflight (la tâche reste celle du plan), et le budget d'effort du tour est au moins celui de ce niveau. C'est le chemin du bouton « Reprendre » du tableau de développement (L3). |
| `session.list` | conversations connues, filtrables par `interface`, `account` |
| `turn.submit` / `turn.queue` / `turn.steer` | message du propriétaire ; `idempotency_key` (id du message Telegram…) : un rejeu ne s'exécute jamais deux fois ; `wait_ms` attend la fin du tour et renvoie `{status, reason, text, tools}` |
| `turn.result` | résultat d'un tour par son `request_id`, plus tard ou après redémarrage (lu dans le journal du noyau) |
| `turn.cancel` | interrompt le tour en cours (`status: cancelled`, run fermé `cancelled`) |
| `approval.list` / `approval.answer` | demandes en attente des sessions ouvertes par l'API ; `allow_once` ou `deny`, par le propriétaire de la session seulement ; sans réponse avant le délai (10 min) = refus |
| `delegate` | `{delegation: delegation.v1 {goal, context?, task?, model? (id ou {id, provider?}), budget_seconds?, output_contract?, constraints?, idempotency_key, parent{run_id, session_id, task_id, depth}}, caller}` → une session `mcp/<caller>/task-<empreinte de la clé>` sans surveillance (preset `api` : lectures permises, toute demande d'accord refusée), son run rangé sous `parent.run_id` (canal `machine`) ; attend la fin dans `budget_seconds` (60–3600, sinon interrompue : `cancelled`, `budget_seconds`) ; même clé = même session, jamais un second tour ; `depth ≥ 3` → 403 `max_depth`. Un `model` nommé est revalidé par Walter Router (`walter-router route - --model`) : refusé → 422 `model_unavailable` avant toute session ; accepté → publié pour le plan du run, walter-llm n'exécute que lui (`exact:`). C'est le chemin de `walter_run` (texte) quand l'instance le lie au moteur. |
| `health` | état, nombre de conversations et d'approbations en attente |

**Statuts d'un tour** : `ok`, `cancelled`, `budget_exhausted` (plafond Walter ou session archivée), `error`,
`interrupted` (processus arrêté), `unknown_outcome`.

**Événements client** (SSE) : `turn.started`, `message.user` (avec `request_id`), `message.assistant`,
`tool.called`, `tool.result`, `approval.requested`, `approval.answered`, `turn.ended` (avec `status`). Les
approbations sont celles de l'API (son identifiant, le seul que `approval.answer` connaît ; redonnées à chaque
abonnement tant qu'elles attendent) : la paire d'audit du noyau (`approval/asked|decided`) n'est pas transmise.

## Portes et permissions

La porte d'une session décide de son preset (`core/security/policy.json`) : `telegram` → `telegram-owner`, `api`
→ `api`, `mode: command` → `command` (lecture seule). Un appelant ne peut que restreindre (`permissions: "command"`),
jamais élargir. Un sous-agent est jugé sous la porte de sa racine. Les demandes (`ask`) des sessions ouvertes par
l'API vont à leur client (boutons Telegram, `approval.answer`), celles d'un sous-agent au client de sa racine ; celles du web gardent la boîte de dialogue web ; une
session `command` ne demande jamais : refusé.

## Fichiers

| Fichier | Contenu |
|---|---|
| `index.mjs` | greffon (`apply`), `EngineApi` (opérations, répondant d'approbation, flux), face HTTP |
| `bindings.mjs` | table d'adresses `<porte>/<compte>/<conversation>` → session du noyau (`@instance/state/core/engine/api/bindings.json`, écriture atomique, 0600) et porte publiée pour la politique |
| `events.mjs` | traduction des événements du noyau, suivi d'une requête jusqu'à la fin de son tour |
| `tests/api.test.mjs` | 11 essais avec un noyau simulé (joués aussi par `core/engine/tests/test_engine_plugins.py`) |

Scénario de bout en bout contre un vrai moteur : `../../scenarios/v1/engine_api_e2e.py` (hôte de test, jamais la
production sauf demande explicite).

## Retour arrière

Moteur natif : l'API fait partie du processus (pas d'interrupteur ; arrêter `walter-engine` l'arrête). Ancien moteur DSH, retour arrière seulement : `[dsh.engine] api = "off"`, `walter harness install dsh --apply`, redémarrage de `dsh-web` : le bloc `dsh-api` du
profil web est retiré, le reste de la composition est inchangé. La table d'adresses reste (aucune session supprimée).
