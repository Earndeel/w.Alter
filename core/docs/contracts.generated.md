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
| memory | capability | Posséder les événements et objets canoniques, leur provenance et les connaissances dérivées. | — |
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
| library | active | Recherche web et lecture de pages | `/walter/capabilities/browse/walter_browse` | capabilities/browse |
| engine | active | Moteurs Camoufox / CloakBrowser (ex ~/.hermes/camoufox-max) | `/walter/capabilities/browse/engine` | capabilities/browse/engine |
| network | active | Sorties réseau (Freebox, Mac, défaut) | `/walter/capabilities/browse/network` | capabilities/browse/network |
| runtime | active | Exécution et extracteurs | `/walter/capabilities/browse/runtime` | capabilities/browse/runtime |

**Limites déclarées :**

- Authenticated HTTP uses managed server-side cookies and refuses cross-origin redirects or anonymous fallback.
- Authenticated interactive browser routes are not qualified by the HTTP fixture.
- Conversational recipes are validated on the local fixture chat UI; a real service needs its own recipe run and its owner's authorization (web_services table of the Router).

## bus

Livrer les événements entre modules et conserver les curseurs de traitement.

Contrat 1.1.0; propriétaire : bus.
Racine actuelle : `/walter/memory`. Cible : `/walter/memory`.

Interfaces : Python emit/Consumer, Postgres LISTEN/NOTIFY.

**Critères de validation :**

- Un consommateur arrêté reprend depuis son curseur sans perdre les événements persistés. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| bus | active | Bus Walter (schéma bus, LISTEN/NOTIFY, curseurs, dead) | `/walter/memory/walter_memory/bus.py` | core/bus |

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
| bridge | active | Pont Colab (GPU à la demande) | `/walter/capabilities/colab/bridge.py` | capabilities/colab |
| mcp | active | Serveur MCP Colab | `/walter/capabilities/colab/mcp` | capabilities/colab |

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
| library | active | Contrôle des appareils (Mac, bureau) | `/walter/capabilities/computer/walter_computer` | capabilities/computer |

**Limites déclarées :**

- No desktop input in health checks.
- Read, pixels, vision and input require explicit grants.
- Cloud vision additionally requires host-only authorization for one exact window; default denied.
- Workflow reservations are cross-process leases with bounded expiry; live Mac qualification tracked separately.

## context

Préparer et ordonner le contexte par message et par sous-agent, et compresser l’historique selon le contrat du harness ; les données canoniques restent dans leurs modules propriétaires.

Contrat 1.3.0; propriétaire : context.
Racine actuelle : `/walter/cognition/context`. Cible : `/walter/cognition/context`.

Interfaces : Python Session (walter_context.compress), Hermes ContextEngine adapter, DSH CompactionEngine adapter, CLI walter-context, CLI walter-context capability router (versioned stable note), Python walter_context.capabilities.TurnNotes, JSON bridge op=capability for trusted module notes, CLI walter-context capability all [--write] (Modules W.Alter layer from walter present notes), HTTP 127.0.0.1:8897 preflight (POST /preflight[?shadow=1], GET /health; CLI walter-context-preflight goes through it), Python walter_context.retrieval.gather and walter_context.assembly.pack, Python walter_context.child.build; CLI walter-context-child (ChildContextSpec v1 JSON), POST /preflight?inject=1 -> plan/text/pack/error; POST /preflight?shadow=1 -> private instance record without injection, CLI walter-context-entrance (Claude Code PostToolUse event on stdin; --report) — large tool outputs on their way in, shadow.

**Critères de validation :**

- Les contraintes, instructions, références et budgets survivent aux checkpoints répétés ou l’opération est refusée. (integration)
- Un corpus fixé à l’avance respecte les seuils de qualité, coût et rétention visible. (live)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| preflight | active | Décision unique par message : ContextPlan (intention, niveau, capacités, voie rapide) | `/walter/cognition/context/walter_context/preflight` | cognition/context/preflight |
| assembly | active | Assemblage du contexte selon le plan (pack) | `/walter/cognition/context/walter_context/assembly.py` | cognition/context |
| child | active | ChildContextSpec : dossier de départ d'un sous-agent | `/walter/cognition/context/walter_context/child.py` | cognition/context |
| compress | active | Moteur de compaction (projection head→record→compact→live) | `/walter/cognition/context/walter_context/compress` | cognition/context/compress |
| recover | active | Retrouver l'original d'une sortie compactée (walter_logs) | `/walter/cognition/context/walter_context/recover.py` | cognition/context |
| dsh-port | active | Prise DSH (injection et compaction) ; deviendra la stratégie context du moteur | `/walter/cognition/context/ports/dsh` | core/engine/plugins |
| bench | active | Bancs (levels, replay, quality, acceptance) | `/walter/cognition/context/bench` | cognition/context/bench |
| session-state | active | État de travail par fil (SessionState v1) | `/walter/cognition/context/contracts/schemas/session-state.v1.json` | cognition/context/contracts |

**Limites déclarées :**

- DSH uses public compaction transactions; checkpoints retain all visible user and assistant dialogue or refuse.
- Hermes runs its native compressor (walter-compress retired 2026-10-21); the walter-context Hermes port is not activated.
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

Interfaces : MCP stdio, walter CLI, CLI contracts, matrix, doctor, Declarative harness compositions, Offline source release and staged installation, walter standby, walter matrix: qualified evidence requires matching source/scenario/version/configuration attestation (bench protocol 2), walter-guardians: strict Incident v1 validation, explicit check failures and bounded notification retry/backoff.

**Critères de validation :**

- Un module optionnel absent ne désactive pas les capacités restantes. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| engine | implemented | Runtime agentique unique de Walter : noyau DSH/Cordis approprié (base adaptable) + greffons et portes Walter ; en service dans /opt/dsh (dsh-web) | `/walter/core/engine` | core/engine |
| engine-contracts | implemented | Schémas Engine API, accueil, délégation, politique, événements, stratégies (brouillons testés) | `/walter/core/engine/contracts` | core/engine/contracts |
| engine-kernel | implemented | Gel du noyau DSH/Cordis (lot E1) : version exacte, verrou, empreintes de l'installation, installation hors ligne reproductible, vérification ; l'installation en service reste /opt/dsh | `/walter/core/engine/kernel` | core/engine/kernel |
| engine-compositions | active | Source de la face du profil web DSH (nom, accueil, durée de connexion), rendue par walter-core dans le bloc géré dsh-face ; valeurs dans la configuration de l'instance (lot E1) | `/walter/core/engine/compositions` | core/engine/compositions |
| engine-plugins | implemented | Stratégies du moteur : intake et events (lot E2 : accueil d'un tour — run, ContextPlan, pack, skills — et fin du run, turn.ended, session.ended) ; policy et budget (lot E3 : politique unique avant chaque outil de chaque agent, plafonds du tour) ; interrupteurs [dsh.engine] intake hook\|shadow\|native et policy off\|enforce | `/walter/core/engine/plugins` | core/engine/plugins |
| security | implemented | Politique d'exécution unique de Walter (lot E3) : policy.json (jamais, classes d'outils, presets par porte, enfant ≤ parent) lue par le greffon policy du moteur (policy.mjs) et par le filet du serveur MCP pour tout client (walter_security) ; mêmes vecteurs d'essai des deux côtés | `/walter/core/security` | core/security |
| engine-api | active | Engine API (lot E4) : porte canonique du moteur pour Telegram, le web, les modules et les tests — ouvrir ou retrouver une conversation (<porte>/<compte>/<conversation> → session du noyau), soumettre (idempotent), suivre (SSE), résultat d'un tour, interrompre, répondre aux approbations ; greffon hôte du profil web, interrupteur [dsh.engine] api off\|on | `/walter/core/interfaces/api` | core/interfaces/api |
| interface-telegram | active | Porte Telegram du moteur (lot E7) : bot propre à Walter, client de l'Engine API uniquement — conversations telegram/<compte>/chat-<id> persistantes, messages idempotents (id Telegram), suivi SSE (écrit…, outils, réponse), /stop, /nouveau, /etat, boutons d'approbation, propriétaire seul ; service walter-telegram | `/walter/core/interfaces/telegram` | core/interfaces/telegram |
| mcp-server | active | Serveur MCP walter : expose les capacités aux agents (Claude Code, Codex, DSH, Hermes) | `/walter/core/server.py` | core/interfaces/mcp |
| capabilities-adapter | active | Adaptateur des outils MCP vers les commandes déclarées des modules | `/walter/core/walter_capabilities.py` | core/interfaces/mcp |
| mcp-toolsets | active | Jeux d'outils MCP par client (WALTER_CLIENT_TAG) | `/walter/core/config/toolsets.toml` | core/interfaces/mcp |
| runtime-hook | active | Adaptateur de cycle de vie des runtimes (preflight, contexte, runs, bus) appelé à chaque message | `/walter/core/hooks/walter_hook.py` | core/interfaces/hooks |
| dsh-hooks | active | Greffon DSH owner-turn (texte du propriétaire pour walter_hook.py) ; remplacé par engine/plugins/intake en mode native | `/walter/core/hooks/dsh` | core/engine/plugins |
| platform | active | Registre, contrats, chemins, instances, raccordements, contrôles (walter …) | `/walter/core/walter_platform` | core/contracts |
| module-catalog | active | Table unique des modules : emplacement actuel, ancien, cible de la vision | `/walter/core/modules/catalog.json` | core/contracts |
| module-registry | active | Registre compilé depuis les contrats (généré, jamais édité à la main) | `/walter/core/modules/registry.json` | core/contracts |
| computer-policy | active | Périmètres Computer Use par interface | `/walter/core/modules/computer-policy.json` | core/security |
| compositions | active | Compositions de harnesses générées par walter-core (sections gérées) | `/walter/core/compositions` | core/engine/compositions |
| dsh-web-ui | active | Personnalisation de l'interface web DSH (couleurs, porte web du propriétaire) | `/walter/core/ports/dsh-web-ui` | core/interfaces/web |
| tool-gateway | active | Passerelle d'outils de walter_run (un processus par run) ; remplacée par le moteur au lot E5 | `/walter/core/bin/walter-tools` | — |
| guardians | active | Lanceur des gardiens de modules (diagnostic, réparation, alerte) | `/walter/core/bin/walter-guardians` | ops/guardians |
| scenarios | active | Scénarios de bout en bout (walter-scenario) | `/walter/core/scenarios` | lab/scenarios |
| browser-session | active | Session navigateur du propriétaire côté serveur (MCP browser_session) — responsabilité de Browse mal placée | `/walter/core/browser_auth.py` | capabilities/browse |
| standby | active | Mise en veille des services à la demande | `/walter/core/walter_platform/standby.py` | ops |

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
| library | active | Lab : bancs, comparaisons, propositions (jamais de déploiement) | `/walter/lab/walter_lab` | lab |
| experiments | active | Expériences et résultats | `/walter/lab/experiments` | lab/experiments |
| computer-use-v2 | experimental | Étude Computer Use V2 (Adaptive Universal Operator) : architecture, prototype en observation, banc ; à l'arrêt | `/walter/lab/computer-use-v2` | lab/computer-use-v2 |

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

Interfaces : OpenAI-compatible :8894, CLI walter-llm call: one exact model/provider, JSON stdin/stdout, no implicit retry or fallback.

**Critères de validation :**

- Un jeton absent ou invalide est refusé et un poste choisi utilise la route attendue. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| gateway | active | Passerelle de modèles OpenAI-compatible (:8894), clés depuis Bitwarden, model=auto suit le plan du run | `/walter/cognition/router/llm/gateway.py` | cognition/router/llm |
| subscriptions | active | Transports par abonnement (Claude, Antigravity, ChatGPT) | `/walter/cognition/router/llm/claude_subscription.py` | cognition/router/llm |

**Limites déclarées :**

- Identified HTTP runs require Memory metadata; unresolved, local_only and redacted_cloud contexts are refused. Untracked legacy requests are outside this check.
- Cost telemetry distinguishes reported, estimated, legacy and unknown; missing usage or a synthetic zero does not prove free execution.

## logs

Conserver les traces accessibles de tous les harnesses dans un journal commun.

Contrat 1.0.0; propriétaire : logs.
Racine actuelle : `/walter/memory`. Cible : `/walter/memory`.

Interfaces : Writer, CLI, MCP.

**Critères de validation :**

- Les sources principales et profils sont collectés avec reprise idempotente après interruption. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| logs-store | active | Journal canonique d'exécution walter_logs (masquage à l'écriture) | `/walter/memory/walter_memory/logs.py` | core/observability |
| logs-watch | active | Synchronisation des journaux de tous les runtimes (inotify) | `/walter/memory/connectors/walter_logs.py` | core/observability |

**Limites déclarées :**

- Only traces made available by the harness can be archived; hidden reasoning cannot be reconstructed.

## memory

Posséder les événements et objets canoniques, leur provenance et les connaissances dérivées.

Contrat 1.2.0; propriétaire : memory.
Racine actuelle : `/walter/memory`. Cible : `/walter/memory`.

Interfaces : Python library, HTTP :8890, CLI, MCP, Overland authenticated HTTP :3010, CLI runs find [RUN_ID|--session SESSION] --open-only: unique open-run metadata run_id/status/privacy_class, ambiguity refused; runs routing RUN_ID: JSONstdin allowlist applied/via/model_id/model/provider/observed_model; runs end RUN_ID: explicit ended/failed/cancelled status, idempotent canonical writer.

**Critères de validation :**

- Les lectures refusent les sources privées, purgées ou rétractées et les fragments périmés. (integration)
- Les décisions datées et remplacées ne sont pas présentées comme des instructions actuelles. (live)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| events | active | Journal canonique core.events (append-only, idempotent) | `/walter/memory/walter_memory/events.py` | cognition/memory |
| gateway | active | Seule porte d'écriture (127.0.0.1:8890) | `/walter/memory/walter_memory/gateway.py` | cognition/memory |
| connectors | active | Connecteurs (hermes, beeper, gmail, calendar, agent_sessions, triage…) | `/walter/memory/connectors` | cognition/memory/connectors |
| organic | active | Mémoire organique V1 (vues, épisodes, périodes, flux) | `/walter/memory/walter_memory/organic.py` | cognition/memory |
| assimilation | active | Assimilation pilotée par le bus (memory.organic) | `/walter/memory/walter_memory/assimilation.py` | cognition/memory |
| runs | active | Run Plane (runs, tâches, épisodes de run) | `/walter/memory/walter_memory/runs.py` | core/orchestration |
| kardex | active | Couche sociale Kardex (schéma kardex) | `/walter/memory/walter_memory/social.py` | cognition/memory/kardex |
| search | active | Index de recherche (search.chunks) | `/walter/memory/walter_memory/search.py` | cognition/memory |
| privacy | active | Classes de confidentialité et règle de lecture | `/walter/memory/walter_memory/privacy.py` | cognition/memory |
| disclosure | active | Contrôle de divulgation des messages sortants | `/walter/memory/walter_memory/disclosure.py` | core/security |
| llm-client | active | Appels de modèles de Memory (refuse local_only, budgets) — lit encore ~/.hermes/.env | `/walter/memory/walter_memory/llm.py` | cognition/memory |
| migrations | active | Migrations Postgres | `/walter/memory/migrations` | cognition/memory/migrations |
| hermes-plugin | active | Fournisseur mémoire walter-memory pour Hermes — à retirer avec Hermes (E7) | `/walter/memory/hermes-plugins` | — |
| overland | active | Réception GPS (Overland, :3010) | `/walter/memory/walter_memory/overland.py` | cognition/memory/connectors |

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
| backup | active | Sauvegardes (pg, state.db, restic, publication git) | `/walter/ops/backup` | ops/backup |
| ops | active | Installation, déploiement, récupération | `/walter/ops/walter_ops` | ops |
| services | active | Dépendances opérationnelles de Walter (bases, bureaux distants, environnements Python partagés, passerelles) : installations, définitions de déploiement et données techniques ; jamais de code de Walter | `/services` | — |
| postgres | implemented | Définition de déploiement de PostgreSQL (compose verrouillé par empreinte, configuration complète) préparée et essayée sur une copie restaurée ; pas en service : la production tourne encore dans le conteneur hindsight-pg sur le volume Docker historique | `/services/postgres` | — |
| kernel-npm-cache | active | Cache npm hors ligne du noyau figé du moteur (lot E1), utilisé par core/engine/kernel/install.sh | `/services/dsh` | — |
| python | active | Environnements Python installés des modules (runtime de walter-python, core, router, llm, raw-vault), déplacés le 2026-11-10 (E9.2a) ; chaque module garde un lien venv ; exclus de restic, reconstruits depuis les verrous des modules | `/services/python` | — |

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
Racine actuelle : `/walter/memory/vault`. Cible : `/walter/memory/vault`.

Interfaces : memory objects library, S3, MCP.

**Critères de validation :**

- Un objet synthétique est écrit, catalogué et relu avec son empreinte et sa confidentialité. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| rawvault-shim | obsolete | Ancienne entrée du Raw Vault ; renvoie vers walter_memory.objects | `/walter/memory/vault/rawvault.py` | — |

**Limites déclarées :**

- Aucune limite supplémentaire déclarée ; les preuves de qualification restent nécessaires.

## router

Choisir les modèles par poste avec décisions et coûts traçables.

Contrat 1.2.0; propriétaire : router.
Racine actuelle : `/walter/cognition/router`. Cible : `/walter/cognition/router`.

Interfaces : CLI, walter-llm task routes, MCP walter_route / walter_run / walter_decide / walter_plans / walter_web, agents' brief (`walter-router brief`, @instance/state/router/brief.md), CLI walter-router schema (public tool contract v1), CLI walter-router docs --write/--check [--offline], CLI walter-router brief --json (versioned orchestrator note v1), CLI walter-router-guardian check | run | status (the module's own maintenance).

**Critères de validation :**

- Un poste renvoie le choix actif et un poste inconnu échoue explicitement sans sélection arbitraire. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| research | active | Collecte des classements et prix (AA, Arena, OpenRouter…) | `/walter/cognition/router/research` | cognition/router/research |
| analysis | active | Analyse, propositions Telegram, alertes (alertes = rôle Hermes à retirer, E6) | `/walter/cognition/router/analysis` | cognition/router/analysis |
| plan | active | Forfaits du propriétaire et quotas | `/walter/cognition/router/plan` | cognition/router/plan |
| serve | active | Choix du modèle par tâche, exécution texte et médias | `/walter/cognition/router/serve` | cognition/router/serve |
| walter-run-loop | active | Boucle de sous-agent de walter_run — seconde boucle agentique, absorbée par le moteur au lot E5 ; terminal retiré le 09/11 | `/walter/cognition/router/serve/text_agent.py` | — |
| oneshot | obsolete | Appels ponctuels via hermes chat --oneshot — rôle Hermes à retirer (E6) | `/walter/cognition/router/serve/oneshot.py` | — |
| interface | active | Page publique de la bibliothèque des modèles | `/walter/cognition/router/interface` | cognition/router/interface |
| store | active | Schéma Postgres models (lecture/écriture) | `/walter/cognition/router/store` | cognition/router/store |
| hermes-plugin | active | Greffon Hermes walter-router — à retirer avec Hermes (E7) | `/walter/cognition/router/hermes-plugins` | — |
| guardian | active | Gardien du Router | `/walter/cognition/router/guardian` | cognition/router/guardian |
| documentation | active | Référence générée (CODE, CONFIGURATION, DATABASE…) contrôlée par les tests | `/walter/cognition/router/documentation.py` | cognition/router/docs |

**Limites déclarées :**

- New model choices remain subject to the owner's approval; no automatic switching introduced.
- Codex subscription catalog and quota collection retain optional Hermes subprocess adapters.
- Text runs execute natively with bounded terminal/file tools; only providers of the selected model are tried, and callers must forward user_notice on failover.
- The guardian lands repairs only in research/, analysis/parse.py, analysis/identity.py, analysis/aliases.json, interface/ and tests/, through deterministic gates; owner choices, execution policy, schema and units are never changed by it.

## runtime

Fournir l’environnement Python partagé des modules Walter.

Contrat 1.0.0; propriétaire : runtime.
Racine actuelle : `/walter/runtime`. Cible : `/walter/runtime`.

Interfaces : command walter-python.

**Critères de validation :**

- walter-python importe les dépendances déclarées dans le lock (unit)
- aucun module n’appelle l’interpréteur d’un autre module (integration)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| python | active | Interpréteur Python partagé des modules | `/walter/runtime/bin/walter-python` | ops/runtime |

**Limites déclarées :**

- The venv is rebuilt from the lock, not exported; a dependency upgrade affects every consumer at once.

## secrets

Gérer les références au coffre et injecter localement les valeurs autorisées.

Contrat 1.1.0; propriétaire : secrets.
Racine actuelle : `/walter/secrets`. Cible : `/walter/secrets`.

Interfaces : safe MCP metadata/reference, local CLI exec/get, Hermes hooks, walter-secret grants / grant access, walter_secrets.grants.

**Critères de validation :**

- Références, erreurs et sorties des processus ne divulguent pas les valeurs du coffre. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| library | active | Accès au coffre Bitwarden sans valeur exposée, autorisations (grants) | `/walter/secrets/walter_secrets` | core/security/secrets |
| compat | obsolete | Anciennes entrées de compatibilité | `/walter/secrets/compat` | — |

**Limites déclarées :**

- Hermes browser-field fill is a host-specific adapter.
- MCP never returns raw secret values; CLI exec suppresses child output.

## skills

Gérer le contenu, la recherche, les propositions et la curation des procédures.

Contrat 1.1.0; propriétaire : skills.
Racine actuelle : `/walter/capabilities/skills`. Cible : `/walter/capabilities/skills`.

Interfaces : HTTP :8891, stdlib client, MCP, Hermes plugin.

**Critères de validation :**

- Une procédure publiée est retrouvée depuis deux harnesses et une proposition reste en brouillon. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)
- Le repère de session ne contient aucun corps de procédure ; un domaine expose les usages et workflows ; une publication active du Curator met à jour l'index sans injecter de candidats à chaque message. (integration)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| core | active | Noyau des skills (store git, cartes Postgres, politique d'exposition, apprentissage) | `/walter/capabilities/skills/walter_skills` | capabilities/skills |
| service | active | Service :8891 | `/walter/capabilities/skills/walter_skills/api.py` | capabilities/skills |
| consumer | active | Consommateur du bus walter-skills-bus | `/walter/capabilities/skills/walter_skills/consumer.py` | capabilities/skills |
| library | active | Bibliothèque de procédures (SKILL.md) | `/walter/capabilities/skills/skills` | capabilities/skills/library |
| archive | obsolete | Skills retirés (réserve) | `/walter/capabilities/skills/archive` | capabilities/skills/archive |

**Limites déclarées :**

- Aucune limite supplémentaire déclarée ; les preuves de qualification restent nécessaires.

## soul

Rendre l'identité de l'instance active pour chaque runtime ; livrer l'identité et les règles par défaut d'une nouvelle instance.

Contrat 1.0.0; propriétaire : soul.
Racine actuelle : `/walter/soul`. Cible : `/walter/soul`.

Interfaces : renderer, walter-soul render/path/sync/check/init, walter_profile MCP.

**Critères de validation :**

- Une modification des sources produit des profils cohérents et détecte les retouches manuelles. (integration)
- Le module et ses données sont reconstruits dans un environnement isolé avec ses intégrations. (recovery)

**Composants :**

| Composant | État | Rôle | Chemin | Cible (vision) |
|---|---|---|---|---|
| renderer | active | Rendu de l'identité vers chaque runtime (SOUL.md, profils) | `/walter/soul/bin/walter-soul` | core/identity |
| runtimes | active | Adaptateurs neutres par runtime | `/walter/soul/runtimes` | core/identity/runtimes |

**Limites déclarées :**

- An instance may keep historical target locations (harness homes, profile workspaces) through its targets override.
