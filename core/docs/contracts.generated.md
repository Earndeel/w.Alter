# Contrats des modules Walter

Généré depuis les manifestes propriétaires. Les scénarios décrivent les critères ; leur réussite est mesurée séparément.

| Module | Niveau | Responsabilité | Dépendances obligatoires |
|---|---|---|---|
| browse | capability | Rechercher, extraire et gérer les parcours web avec un moteur commun. | — |
| bus | foundation | Livrer les événements entre modules et conserver les curseurs de traitement. | memory |
| colab | capability | Préparer et exécuter des travaux de calcul distant qualifiés. | — |
| computer | capability | Observer et manipuler un appareil avec des permissions et cibles explicites. | — |
| context | capability | Préparer et ordonner le contexte par message et par sous-agent, et compresser l’historique selon le contrat du harness ; les données canoniques restent dans leurs modules propriétaires. | — |
| core | foundation | Exposer les capacités et installer les raccordements des harnesses. | — |
| lab | capability | Chercher, mesurer et proposer des améliorations de Walter, sans jamais les appliquer seul. | — |
| llm | capability | Exécuter les appels modèles des consommateurs autorisés via les postes du Router. | router, secrets |
| logs | foundation | Conserver les traces accessibles de tous les harnesses dans un journal commun. | memory |
| memory | capability | Posséder les événements et objets canoniques, leur provenance et les connaissances dérivées. | core |
| ops | foundation | Installer, déployer, versionner, conserver et restaurer le logiciel Walter et ses instances (installer, deploy, git, backup, recovery, guardian), indépendamment des autres modules. | — |
| raw-vault | capability | Conserver les octets originaux et les relier au catalogue canonique. | memory |
| router | capability | Choisir les modèles par poste avec décisions et coûts traçables. | — |
| runtime | foundation | Fournir l’environnement Python partagé des modules Walter. | — |
| secrets | capability | Gérer les références au coffre et injecter localement les valeurs autorisées. | — |
| skills | capability | Gérer le contenu, la recherche, les propositions et la curation des procédures. | bus |
| soul | foundation | Rendre l'identité de l'instance active pour chaque runtime ; livrer l'identité et les règles par défaut d'une nouvelle instance. | — |

## browse

Rechercher, extraire et gérer les parcours web avec un moteur commun.

Contrat 1.0.0; propriétaire : browse.
Racine actuelle : `/walter/capabilities/browse`. Cible : `/walter/capabilities/browse`.

Interfaces : shared request contract, CLI, MCP, Hermes plugin, public client (walter_browse.converse).

**Critères de validation :**

- Une extraction publique passe par le noyau partagé sans processus agent Hermes. (live)
- Une session gérée permet un parcours autorisé sans divulguer ses identifiants. (live)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| library | active | Web search and page reading (the walter_browse facade) | `/walter/capabilities/browse/walter_browse` | capabilities/browse |
| engine | active | Browser engines: Camoufox and CloakBrowser Chromium | `/walter/capabilities/browse/engine` | capabilities/browse/engine |
| network | active | Network exits (the owner's machine, the France exit, default exit, NordVPN per country on demand) | `/walter/capabilities/browse/network` | capabilities/browse/network |
| runtime | active | Execution paths and extractors | `/walter/capabilities/browse/runtime` | capabilities/browse/runtime |

**Limites déclarées :**

- Authenticated HTTP uses managed server-side cookies and refuses cross-origin redirects or anonymous fallback.
- Authenticated interactive browser routes are not qualified by the HTTP fixture.
- Conversational recipes are validated on the local fixture chat UI; a real service needs its own recipe run and its owner's authorization (web_services table of the Router).
- NordVPN exits use the Walter Secrets grant `nordvpn`; Chromium refuses third-party exits; a NordVPN session never receives owner cookies.

## bus

Livrer les événements entre modules et conserver les curseurs de traitement.

Contrat 1.1.0; propriétaire : bus.
Racine actuelle : `/walter/cognition/memory`. Cible : `/walter/cognition/memory`.

Interfaces : Python emit/Consumer, Postgres LISTEN/NOTIFY.

**Critères de validation :**

- Un consommateur arrêté reprend depuis son curseur sans perdre les événements persistés. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| bus | active | Walter bus: schema bus, LISTEN/NOTIFY, per-consumer cursors, dead letters | `/walter/cognition/memory/walter_memory/bus.py` | core/bus |

**Limites déclarées :**

- Livraison sans trou : un consommateur ne lit que les transactions terminées (tx < xmin) ; une transaction ouverte longtemps retarde la livraison sans la perdre (bus.lag held).

## colab

Préparer et exécuter des travaux de calcul distant qualifiés.

Contrat 1.0.0; propriétaire : colab.
Racine actuelle : `/walter/capabilities/colab`. Cible : `/walter/capabilities/colab`.

Interfaces : on_demand.py CLI.

**Critères de validation :**

- Une charge non qualifiée est refusée avant toute allocation de calcul. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| bridge | active | Colab bridge: remote compute on demand | `/walter/capabilities/colab/bridge.py` | capabilities/colab |
| mcp | active | Colab MCP server | `/walter/capabilities/colab/mcp` | capabilities/colab |

**Limites déclarées :**

- GPU remains blocked until prepared artifact validation; modularity work does not remove this guard.
- No remote compute is allocated by modularity checks.

## computer

Observer et manipuler un appareil avec des permissions et cibles explicites.

Contrat 1.0.0; propriétaire : computer.
Racine actuelle : `/walter/capabilities/computer`. Cible : `/walter/capabilities/computer`.

Interfaces : OperatorSessions, MCP computer_use, Hermes plugin.

**Critères de validation :**

- Une tâche synthétique sur le Mac réussit sans accéder aux applications personnelles. (live)
- Les cibles périmées et les accès concurrents non autorisés sont refusés. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| library | active | Device control (Mac desktop) through atomic actions | `/walter/capabilities/computer/walter_computer` | capabilities/computer |

**Limites déclarées :**

- No desktop input in health checks.
- Read, pixels, vision and input require explicit grants.
- Cloud vision additionally requires host-only authorization for one exact window; default denied.
- Workflow reservations are cross-process leases with bounded expiry; live Mac qualification tracked separately.

## context

Préparer et ordonner le contexte par message et par sous-agent, et compresser l’historique selon le contrat du harness ; les données canoniques restent dans leurs modules propriétaires.

Contrat 1.3.0; propriétaire : context.
Racine actuelle : `/walter/cognition/context`. Cible : `/walter/cognition/context`.

Interfaces : Python Session (walter_context.compress), DSH CompactionEngine adapter, CLI walter-context, CLI walter-context capability router (versioned stable note), Python walter_context.capabilities.TurnNotes, JSON bridge op=capability for trusted module notes, CLI walter-context capability all [--write] (Modules W.Alter layer from walter present notes), HTTP 127.0.0.1:8897 preflight (POST /preflight[?shadow=1], GET /health; CLI walter-context-preflight goes through it), Python walter_context.retrieval.gather and walter_context.assembly.pack, Python walter_context.child.build; CLI walter-context-child (ChildContextSpec v1 JSON), POST /preflight?inject=1 -> plan/text/pack/degraded/error (degraded = decision failed, prudent L3 plan, SOCLE A2; pack.cuts = blocks cut to the level budget); POST /preflight?shadow=1 -> private instance record without injection, CLI walter-context-entrance (Claude Code PostToolUse event on stdin; --report) — large tool outputs on their way in, shadow, In-process walter.context.window: globalThis[Symbol.for('walter.context.window')](agent, {plan}, signal) published by the DSH port -> window decision report {applied, reason, warm, turns, tokens, measured_tokens} (SOCLE A1; the kernel isolates its compaction service, the engine's intake plugin calls this entry at each owner turn).

**Critères de validation :**

- Les contraintes, instructions, références et budgets survivent aux checkpoints répétés ou l’opération est refusée. (integration)
- Un corpus fixé à l’avance respecte les seuils de qualité, coût et rétention visible. (live)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| preflight | active | One decision per owner message: the ContextPlan (intent, level, capabilities, fast path) | `/walter/cognition/context/walter_context/preflight` | cognition/context/preflight |
| assembly | active | Context assembly according to the plan (the turn's pack) | `/walter/cognition/context/walter_context/assembly.py` | cognition/context |
| child | active | ChildContextSpec: the starting brief of a sub-agent | `/walter/cognition/context/walter_context/child.py` | cognition/context |
| compress | active | Compaction engine (projection head → record → compact → live) | `/walter/cognition/context/walter_context/compress` | cognition/context/compress |
| recover | active | Retrieve the original of a compacted output (walter_logs) | `/walter/cognition/context/walter_context/recover.py` | cognition/context |
| dsh-port | obsolete | Rollback only since 2026-11-18 (DSH uninstalled): the former DSH port (owner-turn window, checkpoint under pressure, context_recover) | `/walter/cognition/context/ports/dsh` | core/engine/plugins |
| bench | active | Benches (levels, replay, quality, acceptance) | `/walter/cognition/context/bench` | cognition/context/bench |
| session-state | active | Working state per thread (SessionState v1) | `/walter/cognition/context/contracts/schemas/session-state.v1.json` | cognition/context/contracts |

**Limites déclarées :**

- DSH uses public compaction transactions; checkpoints retain all visible user and assistant dialogue or refuse.
- Structural and known-answer tests do not certify semantic model quality.
- Capability-note preparation does not activate the lot-4 composer or inject into an unconnected host.
- Memory, Skills, Core, Router, Logs and Soul are optional at module startup; their dependent operations degrade or fail when unavailable.
- retrieval, assembly, preflight and child are implemented; their availability is separate from activation and semantic quality.
- Source failures omit only the affected retrieval/child block and leave a note; absence of a block does not prove absence of matching knowledge.
- Preflight can write plan metadata through the Memory runs CLI; it does not own canonical memory, notebooks or procedures.
- Local compression has no general semantic quality proof; recoverability depends on source availability and privacy.
- Entrance runs in shadow only: walter_logs records the text the model saw, so replacing an output needs the hook to journal the original first; [entrance].mode=on is refused until then.

## core

Exposer les capacités et installer les raccordements des harnesses.

Contrat 1.1.0; propriétaire : core.
Racine actuelle : `/walter/core`. Cible : `/walter/core`.

Interfaces : MCP stdio, walter CLI, CLI contracts, matrix, doctor, Declarative harness compositions, Offline source release and staged installation, walter standby, walter matrix: qualified evidence requires matching source/scenario/version/configuration attestation (bench protocol 2), walter-guardians: strict Incident v1 validation, explicit check failures and bounded notification retry/backoff, Python walter_beeper.BeeperClient: native Beeper REST/WS; named Secrets grants, MCP beeper_read; beeper_send_message only through local Walter Engine with policy enforce.

**Critères de validation :**

- Un module optionnel absent ne désactive pas les capacités restantes. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| engine | implemented | Walter Engine, W.Alter's single agent runtime: native walter_engine (walter-engine.service since 2026-11-17: loop, sessions, tools, Python kernel, sub-agents, tasks, Engine API); the former DSH/Cordis kernel is uninstalled (rollback archive only) | `/walter/core/engine` | core/engine |
| engine-contracts | implemented | Engine API, intake, delegation, policy, events and strategy schemas (tested drafts) | `/walter/core/engine/contracts` | core/engine/contracts |
| engine-kernel | obsolete | Freeze of the DSH/Cordis kernel (lot E1); DSH uninstalled on 2026-11-18: rollback kit only, `walter engine kernel` says installed=false | `/walter/core/engine/kernel` | core/engine/kernel |
| engine-compositions | obsolete | Rollback only since 2026-11-18 (DSH uninstalled): source of the former DSH web profile face | `/walter/core/engine/compositions` | core/engine/compositions |
| engine-plugins | obsolete | Rollback only since 2026-11-18 (DSH uninstalled): DSH Node plugins (intake, events, policy, budget); only engine/plugins/python/runtime still serves the native engine (component engine-python) | `/walter/core/engine/plugins` | core/engine/plugins |
| engine-python | implemented | The engine's python tool: a persistent Python kernel per conversation in an unprivileged systemd bubble (only its folder writable, local network refused); W.Alter tools from Python under the policy, background tasks, sub-agents | `/walter/core/engine/plugins/python` | core/engine/plugins |
| security | implemented | W.Alter's single execution policy (lot E3): policy.json (never-list, tool classes, presets per door, child ≤ parent), applied by the engine and by the MCP server's guard for every client | `/walter/core/security` | core/security |
| engine-api | obsolete | Rollback only since 2026-11-18 (DSH uninstalled): the former Node implementation of the Engine API; the native engine serves the same contract (engine/walter_engine/api.py) | `/walter/core/interfaces/api` | core/interfaces/api |
| interface-telegram | active | Telegram door of the engine (lot E7): W.Alter's own bot, an Engine API client only — persistent conversations, idempotent messages, live progress, /stop, /nouveau, /etat, owner only; service walter-telegram | `/walter/core/interfaces/telegram` | core/interfaces/telegram |
| mcp-server | active | The walter MCP server: exposes W.Alter's capabilities to agents (Walter Engine, Claude Code, Codex) | `/walter/core/server.py` | core/interfaces/mcp |
| capabilities-adapter | active | Adapter from MCP tools to the modules' declared commands | `/walter/core/walter_capabilities.py` | core/interfaces/mcp |
| mcp-toolsets | active | MCP toolsets per client (WALTER_CLIENT_TAG); tools not listed stay reachable through walter_call | `/walter/core/config/toolsets.toml` | core/interfaces/mcp |
| runtime-hook | active | Runtime lifecycle adapter for external agents (preflight, context, runs, bus), called at each message | `/walter/core/hooks/walter_hook.py` | core/interfaces/hooks |
| dsh-hooks | obsolete | Rollback only since 2026-11-18 (DSH uninstalled): the DSH owner-turn plugin | `/walter/core/hooks/dsh` | core/engine/plugins |
| platform | active | Registry, contracts, paths, instances, harness connections, checks (the walter CLI), and module presentation (module_guide) | `/walter/core/walter_platform` | core/contracts |
| module-catalog | active | Single table of modules: current location, former location, vision target | `/walter/core/modules/catalog.json` | core/contracts |
| module-registry | active | Registry compiled from the contracts (generated, never edited by hand) | `/walter/core/modules/registry.json` | core/contracts |
| computer-policy | active | Computer Use scopes per interface | `/walter/core/modules/computer-policy.json` | core/security |
| compositions | active | Harness compositions generated by walter-core (managed sections) | `/walter/core/compositions` | core/engine/compositions |
| dsh-web-ui | obsolete | Rollback only since 2026-11-18 (DSH uninstalled): the former DSH web interface customisation | `/walter/core/ports/dsh-web-ui` | core/interfaces/web |
| web-panels | active | Web interface panels: pages of other W.Alter modules (development board…) relayed read-only behind the interface's sign-in | `/walter/core/interfaces/web/panels` | core/interfaces/web |
| tool-gateway | active | Tool gateway of walter_run (one process per run) | `/walter/core/bin/walter-tools` | — |
| guardians | active | Launcher of the module guardians (diagnosis, repair, alert) | `/walter/core/bin/walter-guardians` | ops/guardians |
| scenarios | active | End-to-end scenarios (walter-scenario) | `/walter/core/scenarios` | lab/scenarios |
| browser-session | active | The owner's server-side browser session (MCP browser_session); belongs to Browse, misplaced here | `/walter/core/browser_auth.py` | capabilities/browse |
| standby | active | On-demand standby of services | `/walter/core/walter_platform/standby.py` | ops |
| deploy-check | active | Deployment freshness: each long-running service compares its start time with the code it loads; guarded repair by the core guardian (restart) | `/walter/core/walter_platform/deploy.py` | ops |
| beeper | implemented | Native Beeper channel (REST/WebSocket); reads and sends go through Walter Engine's policy | `/walter/core/walter_beeper.py` | core/interfaces/beeper |

**Limites déclarées :**

- MCP client must reconnect to discover newly installed tools.
- CLI attachment installs common MCP; context/model/lifecycle bindings are checked independently.

## lab

Chercher, mesurer et proposer des améliorations de Walter, sans jamais les appliquer seul.

Contrat 0.1.1; propriétaire : lab.
Racine actuelle : `/walter/lab`. Cible : `/walter/lab`.

Interfaces : CLI walter-lab status|run|history|list, Experiment v1 (experiments/*.yaml), CLI walter-lab sandbox run|probe, Python walter_lab.sandbox.run.

**Critères de validation :**

- La décision proposée découle de la règle écrite avant les essais. (unit)
- Liens, hardlinks multiples et fichiers spéciaux sont refusés ; une course de remplacement ne lit pas hors de la source et un export ne fusionne jamais une destination existante. (unit)
- Checkpoints et rapport final gardent le même protocole sans écrire les valeurs d’environnement. (unit)
- Le probe Docker réel vérifie UID, réseau, accès hôte et écritures racine ; timeout ou code non nul sont des échecs. (integration)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| library | active | Lab: benches, comparisons, proposals (never a deployment) | `/walter/lab/walter_lab` | lab |
| experiments | active | Experiments and results | `/walter/lab/experiments` | lab/experiments |
| computer-use-v2 | experimental | Computer Use V2 study (Adaptive Universal Operator): architecture, observed prototype, bench; stopped | `/walter/lab/computer-use-v2` | lab/computer-use-v2 |

**Limites déclarées :**

- Paused until production (owner decision 2026-10-29): no experiment on Lab's own initiative; `run` needs the owner's explicit request (--requested-by owner --reason), recorded in the report. Mode in @instance/config/lab/lab.toml (module default: paused).
- Scope: transverse R&D and global self-improvement only. Each module keeps its own research, refresh, learning and guardian (Router cycle, Skills curator, Browse recipes); none of them needs Lab.
- The shared bench (walter-scenario, scenarios, qualifications read by `walter matrix`) is never paused; it still lives in core until its public interfaces exist (addendum 2026-10-29, F).
- Scenario experiments inherit host permissions and environment; sandbox execution is a separate explicit interface.
- Proposals only: nothing is ever applied by Lab.
- No external-source scout or runtime-neutral runtime comparison yet.
- Sandbox uses an unprivileged Docker container with no network; host copies reject links and special files and have byte/entry/depth limits.
- Known credential names are excluded from input; arbitrary secret contents still require an approved sanitised source and image.
- The writable bind has no disk quota during execution; unsuitable where a hard disk bound is required. Docker shares the host kernel.
- Sandbox requires a reviewed image already present locally; no automatic image pull or network mode.
- After backend changes run the real sandbox probe; mocked host-boundary tests do not qualify Docker isolation.

## llm

Exécuter les appels modèles des consommateurs autorisés via les postes du Router.

Contrat 1.2.0; propriétaire : llm.
Racine actuelle : `/walter/cognition/router/llm`. Cible : `/walter/cognition/router/llm`.

Interfaces : OpenAI-compatible :8894, POST /v1/decisions {state, questions, samples?, model?|models?, paid_floor_usd?} on the Router's decision chain; POST /v1/rerank {query, documents, top_n?, model?} on the rerank poste; GET /v1/balance (SOCLE A6), CLI walter-llm call: one exact model/provider, JSON stdin/stdout, no implicit retry or fallback.

**Critères de validation :**

- Un jeton absent ou invalide est refusé et un poste choisi utilise la route attendue. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| gateway | active | OpenAI-compatible model gateway (:8894): keys from the vault, model = a Router poste | `/walter/cognition/router/llm/gateway.py` | cognition/router/llm |
| subscriptions | active | Subscription transports (Claude, Antigravity, ChatGPT/Codex) | `/walter/cognition/router/llm/claude_subscription.py` | cognition/router/llm |

**Limites déclarées :**

- Identified HTTP runs require Memory metadata; unresolved, local_only and redacted_cloud contexts are refused. Untracked legacy requests are outside this check.
- Cost telemetry distinguishes reported, estimated, legacy and unknown; missing usage or a synthetic zero does not prove free execution.

## logs

Conserver les traces accessibles de tous les harnesses dans un journal commun.

Contrat 1.0.0; propriétaire : logs.
Racine actuelle : `/walter/cognition/memory`. Cible : `/walter/cognition/memory`.

Interfaces : Writer, CLI, MCP.

**Critères de validation :**

- Les sources principales et profils sont collectés avec reprise idempotente après interruption. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| logs-store | active | Canonical execution journal walter_logs (secrets masked at write) | `/walter/cognition/memory/walter_memory/logs.py` | core/observability |
| logs-watch | active | Synchronisation of every runtime's logs (inotify) | `/walter/cognition/memory/connectors/walter_logs.py` | core/observability |

**Limites déclarées :**

- Only traces made available by the harness can be archived; hidden reasoning cannot be reconstructed.

## memory

Posséder les événements et objets canoniques, leur provenance et les connaissances dérivées.

Contrat 1.2.0; propriétaire : memory.
Racine actuelle : `/walter/cognition/memory`. Cible : `/walter/cognition/memory`.

Interfaces : Python library, HTTP :8890, CLI, MCP, Overland authenticated HTTP :3010, CLI runs find [RUN_ID|--session SESSION] --open-only: unique open-run metadata run_id/status/privacy_class, ambiguity refused; runs routing RUN_ID: JSONstdin allowlist applied/via/model_id/model/provider/observed_model; runs end RUN_ID: explicit ended/failed/cancelled status, idempotent canonical writer, HTTP :8890 socle A3/A4: POST /v1/tasks/list {thread_id?, session_id?, status?, limit} -> {tasks: [{task_id, goal, status, thread_id, updated_at, progress, attempts, last_outcome}]}; POST /v1/tasks/update {task_id, status?, progress?, result?, note?}; POST /v1/experience {thread_id?, query?, limit} -> {items: [{at, run_id, status, summary, errors, lessons, solutions, pending}]}; /v1/runs/end accepts outcome; /v1/runs/start origin accepts interface, engine_session, request_id; /v1/context accepts thread_id (layers tasks, experience), CLI tasks list|show|update|sweep|triage-redecide [--execute] [--channels owner|all|a,b]; CLI experience [--thread] [--query], Beeper connector: WS -> ingestion.jobs beeper_events -> canonical core.events/media/bus; profile-scoped cursors in existing checkpoints.

**Critères de validation :**

- Les lectures refusent les sources privées, purgées ou rétractées et les fragments périmés. (integration)
- Les décisions datées et remplacées ne sont pas présentées comme des instructions actuelles. (live)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| events | active | Canonical journal core.events (append-only, idempotent) | `/walter/cognition/memory/walter_memory/events.py` | cognition/memory |
| media | active | Derivation of Raw Vault media: audio → transcript (stt poste), document → local extraction, image → OCR/caption (vision poste, disabled); driven by the bus (memory.object) | `/walter/cognition/memory/walter_memory/media.py` | cognition/memory |
| gateway | active | The only write door (127.0.0.1:8890) | `/walter/cognition/memory/walter_memory/gateway.py` | cognition/memory |
| connectors | active | Connectors (beeper, gmail, calendar, agent_sessions, triage…) | `/walter/cognition/memory/connectors` | cognition/memory/connectors |
| organic | active | Organic memory V1 (views, episodes, periods, flows) | `/walter/cognition/memory/walter_memory/organic.py` | cognition/memory |
| assimilation | active | Bus-driven assimilation (memory.organic) | `/walter/cognition/memory/walter_memory/assimilation.py` | cognition/memory |
| runs | active | Run plane: runs, delegated tasks and the owner's durable tasks, run episodes and experience | `/walter/cognition/memory/walter_memory/runs.py` | core/orchestration |
| kardex | active | Kardex social layer (schema kardex) | `/walter/cognition/memory/walter_memory/social.py` | cognition/memory/kardex |
| search | active | Search index (search.chunks) | `/walter/cognition/memory/walter_memory/search.py` | cognition/memory |
| privacy | active | Privacy classes and reading rule | `/walter/cognition/memory/walter_memory/privacy.py` | cognition/memory |
| disclosure | active | Disclosure check of outgoing messages | `/walter/cognition/memory/walter_memory/disclosure.py` | core/security |
| llm-client | active | Memory's model calls (refuses local_only, budgets); keys through Walter Secrets grants, no file fallback | `/walter/cognition/memory/walter_memory/llm.py` | cognition/memory |
| migrations | active | PostgreSQL migrations | `/walter/cognition/memory/migrations` | cognition/memory/migrations |
| overland | active | GPS reception (Overland, :3010) | `/walter/cognition/memory/walter_memory/overland.py` | cognition/memory/connectors |
| beeper-native | implemented | Event-driven Beeper ingestion; HTTP catch-up and canonical deduplication | `/walter/cognition/memory/connectors/beeper_watch.py` | cognition/memory/connectors |

**Limites déclarées :**

- Canonical reads exclude stale, retracted, private and unprovenanced legacy cognitive rows.
- Wild profile reads are refused by the cloud-safe port; local-only history remains local.
- Existing desktop provider instances change on next session initialization; not force-restarted.

## ops

Installer, déployer, versionner, conserver et restaurer le logiciel Walter et ses instances (installer, deploy, git, backup, recovery, guardian), indépendamment des autres modules.

Contrat 0.2.0; propriétaire : ops.
Racine actuelle : `/walter/ops`. Cible : `/walter/ops`.

Interfaces : CLI walter-ops backup|git|check|recovery|deploy|status (install, onboard: planned), CLI walter-ops install migrations-check [--keep-dumps DIR] (Walter Clean, PostgreSQL part: replay every module's migrations on a disposable database, compare the structure with the live one), CLI walter-ops install data-check (every table classified by its module's contracts/data-classes.json; reference rows searched for the instance's private markers, counts only), CLI walter-ops install seed-export DIR | clean-db-check [--seeds DIR | --keep-seeds DIR] (Walter Clean database built from migrations + reference rows on a disposable PostgreSQL, proven marker-free), CLI walter-backup status|check|run|verify|git|checkpoint|checkpoints (compatibility alias, same outputs), CLI walter-ops backup env <pg|statedb|offsite|restore_test> (shell parameters of the backup jobs), Incident v1 (check) for the guardian supervisor.

**Critères de validation :**

- status et check répondent avec Router, Memory et Hermes arrêtés. (integration)
- Une dérive de registre n'empêche ni la sauvegarde ni le rapport de santé. (integration)
- Les caches déjà suivis et le travail non suivi ancien déclenchent un warning G0 ; archives et rapports conservés sont distingués, sans suppression automatique. (unit)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| backup | active | Backups (PostgreSQL, restic offsite, git publication) | `/walter/ops/backup` | ops/backup |
| ops | active | Installation, deployment, recovery | `/walter/ops/walter_ops` | ops |
| services | active | W.Alter's operational dependencies (databases, remote desktops, shared Python environments, gateways): installations, deployment definitions and technical data; never W.Alter code | `/services` | — |
| postgres | active | W.Alter's PostgreSQL: container walter-pg (127.0.0.1:5433), data in /services/postgres/data, settings in config/, compose locked by fingerprint | `/services/postgres` | — |
| python | active | Installed Python environments of the modules (walter-python runtime, core, router, llm, raw-vault); excluded from restic, rebuilt from the modules' locks | `/services/python` | — |
| webtop | active | XFCE desktop in a container (Browse, Computer); compose locked by fingerprint | `/services/webtop` | — |
| browse-display | active | Selkies display (X :101) of W.Alter's browser, started by walter-browse-display.service | `/services/browse-display` | — |
| flaresolverr | active | FlareSolverr (127.0.0.1:8191) for web search; no data | `/services/flaresolverr` | — |
| nordvpn-proxy | active | Settings of Browse's NordVPN per-country exits, opened on demand by walter-wg-exit | `/services/nordvpn-proxy` | — |
| raw-vault-s3 | active | Raw Vault as S3 (127.0.0.1:8899, rclone); keys read from the instance's bootstrap | `/services/raw-vault-s3` | — |
| cloudflared | active | Cloudflare tunnel (the instance's public ingress); settings and credentials (0600) in config/ | `/services/cloudflared` | — |
| devboard | experimental | W.Alter's development board: projects, pending agreements, replaced decisions, documents, agents' live activity (tailnet page, read-only) | `/walter/ops/devboard` | ops/devboard |

**Limites déclarées :**

- Renamed from walter-backup on 2026-10-29 (owner decision): compatibility kept — command walter-backup, paths /walter/backup and /opt/walter-backup, unit names, config @instance/config/backup and state @instance/state/backup (the backup sub-component keeps its name).
- installer: the database of Walter Clean is built and proven (install migrations-check, data-check, clean-db-check; bench scenarios clean-migrations, clean-database); clean-install of the software, onboarding and personal-restore are designed, not built yet (walter-ops install clean|personal and onboard answer 'planned').
- deploy wraps the core platform's release/install/export; Ops does not own the other modules' code, contracts or migrations.
- Backup scripts (pg, statedb, offsite, restore test) moved into backup/scripts on 2026-10-29, each qualified by a real run; host paths /usr/local/sbin/walter-* link to them. Every location comes from the instance (walter-ops backup env <kind>). The isolated restore drill stays in Walter Memory.
- Restores are described, never executed by the tool.
- A git checkpoint holds tracked files only; untracked files are listed, not captured.
- Optional modules: memory (Raw Vault sample of verify), core (walter contracts for conformity).
- Repository hygiene reports G0 warnings only; it never removes, stages or commits files.
- Uncommitted age is estimated from visible file mtimes; touching/deleting a file limits that estimate.
- Configured preserved evidence paths remain visible but are excluded from hygiene warnings; intentional compatibility is not inferred to be obsolete.

## raw-vault

Conserver les octets originaux et les relier au catalogue canonique.

Contrat 1.0.0; propriétaire : raw-vault.
Racine actuelle : `/walter/cognition/memory/vault`. Cible : `/walter/cognition/memory/vault`.

Interfaces : memory objects library, S3, MCP.

**Critères de validation :**

- Un objet synthétique est écrit, catalogué et relu avec son empreinte et sa confidentialité. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| rawvault-shim | obsolete | Former Raw Vault entry point; forwards to walter_memory.objects | `/walter/cognition/memory/vault/rawvault.py` | — |

**Limites déclarées :**

- Aucune limite supplémentaire déclarée ; les preuves de qualification restent nécessaires.

## router

Choisir les modèles par poste avec décisions et coûts traçables.

Contrat 1.2.0; propriétaire : router.
Racine actuelle : `/walter/cognition/router`. Cible : `/walter/cognition/router`.

Interfaces : CLI, walter-llm task routes, MCP walter_route / walter_run / walter_decide / walter_plans / walter_web / audio_transcribe, CLI walter-router transcribe FILE… (stt poste via walter-llm), agents' brief (`walter-router brief`, @instance/state/router/brief.md), CLI walter-router schema (public tool contract v1), CLI walter-router docs --write/--check [--offline], CLI walter-router brief --json (versioned orchestrator note v1), CLI walter-router-guardian check | run | status (the module's own maintenance).

**Critères de validation :**

- Un poste renvoie le choix actif et un poste inconnu échoue explicitement sans sélection arbitraire. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| research | active | Collection of leaderboards and prices (Artificial Analysis, Arena, OpenRouter…) | `/walter/cognition/router/research` | cognition/router/research |
| analysis | active | Analysis, Telegram proposals, alerts | `/walter/cognition/router/analysis` | cognition/router/analysis |
| plan | active | The owner's plans and quotas | `/walter/cognition/router/plan` | cognition/router/plan |
| serve | active | Model choice per task, text and media execution | `/walter/cognition/router/serve` | cognition/router/serve |
| oneshot | active | The Router's one-shot answers: direct walter-llm (economical poste) or delegation to Walter Engine | `/walter/cognition/router/serve/oneshot.py` | — |
| interface | active | Public model library page | `/walter/cognition/router/interface` | cognition/router/interface |
| store | active | PostgreSQL schema models (read/write) | `/walter/cognition/router/store` | cognition/router/store |
| guardian | active | The Router's guardian | `/walter/cognition/router/guardian` | cognition/router/guardian |
| documentation | active | Generated reference (code, configuration, database…) checked by the tests | `/walter/cognition/router/documentation.py` | cognition/router/docs |

**Limites déclarées :**

- New model choices remain subject to the owner's approval; no automatic switching introduced.
- Text runs execute natively with bounded terminal/file tools; only providers of the selected model are tried, and callers must forward user_notice on failover.
- The guardian lands repairs only in research/, analysis/parse.py, analysis/identity.py, analysis/aliases.json, interface/ and tests/, through deterministic gates; owner choices, execution policy, schema and units are never changed by it.

## runtime

Fournir l’environnement Python partagé des modules Walter.

Contrat 1.0.0; propriétaire : runtime.
Racine actuelle : `/walter/ops/runtime`. Cible : `/walter/ops/runtime`.

Interfaces : command walter-python.

**Critères de validation :**

- walter-python importe les dépendances déclarées dans le lock (unit)
- aucun module n’appelle l’interpréteur d’un autre module (integration)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| python | active | Shared Python interpreter of the modules | `/walter/ops/runtime/bin/walter-python` | ops/runtime |

**Limites déclarées :**

- The venv is rebuilt from the lock, not exported; a dependency upgrade affects every consumer at once.

## secrets

Gérer les références au coffre et injecter localement les valeurs autorisées.

Contrat 1.1.0; propriétaire : secrets.
Racine actuelle : `/walter/core/security/secrets`. Cible : `/walter/core/security/secrets`.

Interfaces : safe MCP metadata/reference, local CLI exec/get, Hermes hooks, walter-secret grants / grant access, walter-secret grant env / grant exec (injection ciblée), walter_secrets.grants.

**Critères de validation :**

- Références, erreurs et sorties des processus ne divulguent pas les valeurs du coffre. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| library | active | Access to the Bitwarden vault without exposing values; grants | `/walter/core/security/secrets/walter_secrets` | core/security/secrets |
| walter-cloudflare | active | Targeted injection of Cloudflare credentials (grants cloudflare-api, cloudflare-workers-ai) into a third-party command; fails closed | `/walter/core/security/secrets/bin/walter-cloudflare` | core/security/secrets |
| compat | obsolete | Former compatibility entry points | `/walter/core/security/secrets/compat` | — |

**Limites déclarées :**

- Hermes browser-field fill is a host-specific adapter.
- MCP never returns raw secret values; CLI exec suppresses child output.

## skills

Gérer le contenu, la recherche, les propositions et la curation des procédures.

Contrat 1.1.0; propriétaire : skills.
Racine actuelle : `/walter/capabilities/skills`. Cible : `/walter/capabilities/skills`.

Interfaces : HTTP :8891, stdlib client, MCP.

**Critères de validation :**

- Une procédure publiée est retrouvée depuis deux harnesses et une proposition reste en brouillon. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)
- Le repère de session ne contient aucun corps de procédure ; un domaine expose les usages et workflows ; une publication active du Curator met à jour l'index sans injecter de candidats à chaque message. (integration)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| core | active | Skills core (git store, PostgreSQL cards, exposure policy, learning) | `/walter/capabilities/skills/walter_skills` | capabilities/skills |
| service | active | Service :8891 | `/walter/capabilities/skills/walter_skills/api.py` | capabilities/skills |
| consumer | active | Bus consumer walter-skills-bus | `/walter/capabilities/skills/walter_skills/consumer.py` | capabilities/skills |
| library | active | Library of procedures (SKILL.md) | `/walter/capabilities/skills/skills` | capabilities/skills/library |
| archive | obsolete | Retired skills (reserve) | `/walter/capabilities/skills/archive` | capabilities/skills/archive |

**Limites déclarées :**

- Aucune limite supplémentaire déclarée ; les preuves de qualification restent nécessaires.

## soul

Rendre l'identité de l'instance active pour chaque runtime ; livrer l'identité et les règles par défaut d'une nouvelle instance.

Contrat 1.0.0; propriétaire : soul.
Racine actuelle : `/walter/core/identity`. Cible : `/walter/core/identity`.

Interfaces : renderer, walter-soul render/path/sync/check/init, walter_profile MCP.

**Critères de validation :**

- Une modification des sources produit des profils cohérents et détecte les retouches manuelles. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| renderer | active | Renders the identity for each runtime (Soul, conduct, profiles) | `/walter/core/identity/bin/walter-soul` | core/identity |
| runtimes | active | Neutral adapters per runtime | `/walter/core/identity/runtimes` | core/identity/runtimes |

**Limites déclarées :**

- An instance may keep historical target locations (harness homes, profile workspaces) through its targets override.
