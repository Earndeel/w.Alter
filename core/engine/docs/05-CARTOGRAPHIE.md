# Cartographie : arborescence actuelle → architecture cible

| | |
|---|---|
| **Rôle** | Établir, pour chaque emplacement actuel de Walter, son emplacement cible de la vision, ses dépendances et ce qui doit disparaître. Base de la convergence architecturale (objectif B) et du lot E9. |
| **Propriétaire** | walter-core (exécution des déplacements : walter-ops, un module à la fois). |
| **État** | Inventaire relevé le **09/11/2026** sur la VM, mis à jour le même jour après les arbitrages complémentaires de Monsieur (`/services`, PostgreSQL, Miroshark, ombre de Computer Use). **Aucun module n'est déplacé.** Faits : retrait de Miroshark et de `computer-use-v2-shadow`, création de `/services` (définition PostgreSQL préparée, pas en service ; cache du noyau). Les cibles marquées *à valider* attendent une décision de Monsieur. |
| **Ne fait pas** | Ne remplace pas le catalogue des modules : pour les 17 modules et leurs 83 composants, la source est `core/modules/catalog.json` (`vision_target`) et les contrats (`components[].vision_target`), visibles par `walter layout` et `docs/contracts.generated.md`. Ce document couvre ce que le registre ne décrit pas (hôte, services, instance, dossiers annexes) et explique les déplacements. |
| **Contrats** | Règles de déplacement : `03-MIGRATION.md` § E9 ; résolution des chemins : `walter path`, `walter instance` (jamais de chemin en dur). |

## 1. Règles de la cartographie

1. **Une seule table des emplacements de modules** : le catalogue. Chaque module y porte désormais `vision_target`.
   `walter layout` montre l'emplacement actuel, la cible et `vision.reached` (3 sur 17 aujourd'hui : core, lab, ops).
   La résolution ne change pas avant le déplacement réel.
2. **Déplacer n'est pas réécrire.** Un module garde son code, ses interfaces publiques (commandes, ports, outils MCP,
   noms d'événements) et ses données. Seul son dossier change, avec un lien de compatibilité vérifié.
3. **Une responsabilité, un emplacement.** Quand un composant est mal placé (§ 4), il rejoint son propriétaire en
   même temps que son module, jamais en parallèle d'un autre changement.
4. **Aucune référence supprimée sans preuve qu'elle n'est plus utilisée** (recherche dans le code, les unités,
   les configurations, les sauvegardes, les skills, `walter_logs` sur 30 jours).

## 2. Modules Walter (`/walter`)

| Module (catalogue) | Aujourd'hui | Cible (vision) | Liens de compatibilité existants | Remarque |
|---|---|---|---|---|
| core | `/walter/core` | `/walter/core` (éclaté en sous-dossiers, § 4) | `/opt/walter-core` | Contient aujourd'hui des pièces d'interfaces, de contrats, de sécurité, d'ops et de Lab |
| bus | `/walter/memory` (`walter_memory/bus.py`) | `/walter/core/bus` | — | Le code reste une bibliothèque ; seul son emplacement change |
| logs (walter_logs) | `/walter/memory` | `/walter/core/observability` *à valider* | — | Arbitrage du 09/11 : observabilité du Core. La vision ne nomme pas ce dossier : nom à confirmer |
| memory | `/walter/memory` | `/walter/cognition/memory` | `/opt/walter-memory` | — |
| raw-vault | `/walter/memory/vault` | `/walter/cognition/memory/vault` | `/opt/walter-raw-vault` | Reste à Memory (arbitrage du 09/11) |
| context | `/walter/context` | `/walter/cognition/context` | `/opt/walter-context` | — |
| router | `/walter/router` | `/walter/cognition/router` | `/opt/walter-router` | — |
| llm | `/walter/router/llm` | `/walter/cognition/router/llm` | `/opt/walter-llm` | Passerelle de modèles = Router (arbitrage du 09/11) |
| skills | `/walter/skills` | `/walter/capabilities/skills` | `/opt/walter-skills` | — |
| browse | `/walter/browse` | `/walter/capabilities/browse` | `/opt/walter-browse` | — |
| computer | `/walter/computer` | `/walter/capabilities/computer` | `/opt/walter-computer` | — |
| colab | `/walter/colab` | `/walter/capabilities/colab` | `/opt/walter-colab` | Pas de README de module (contrôle documentaire) |
| soul | `/walter/soul` | `/walter/core/identity` | `/opt/walter-soul` | La vision : « identity : gestion de Soul » |
| secrets | `/walter/secrets` | `/walter/core/security/secrets` | `/opt/walter-secrets` | La vision : « security : permissions, accès aux secrets » |
| runtime (Python partagé) | `/walter/runtime` (code, verrous **et** environnement installé `venv/`) | code et verrous : `/walter/ops/runtime` *à valider* ; environnement installé : `/services/python/<environnement>` (arbitrage du 09/11) | — | Absent de la vision. Les venv propres de core, router, llm et raw-vault suivent la même règle |
| ops | `/walter/ops` | `/walter/ops` | `/walter/backup`, `/opt/walter-backup`, `/opt/walter-ops` | — |
| lab | `/walter/lab` | `/walter/lab` | `/opt/walter-lab` | — |
| docs (global) | `/walter/docs` | `/walter/docs` (niveau 1 seulement, § 6) | `~/.hermes/docs/walter-memory` | — |
| user | lien `/walter/user` → `/user/Lucas` | à retirer | — | Un module ne doit pas joindre l'instance par chemin ; `walter instance` suffit |

## 3. Le moteur

| Aujourd'hui | Cible | Quand |
|---|---|---|
| `/opt/dsh` : paquet npm installé (533 Mo, hors git) | **Gel technique** à E1, sans déplacement : version exacte, verrou, empreintes, cache hors ligne. L'installation reconstruisible vit hors git ; son emplacement définitif est décidé à E9 selon la place disque | E1, puis E9 |
| `/opt/dsh/home` (DSH_HOME : sessions, `cordis.patch.yml`, hooks) | Sessions → état de l'instance (`@instance/state/engine`) ; configuration générée → `core/engine/compositions` | E9 (sessions), E1 (composition générée) |
| `/opt/dsh/test-home` | Banc isolé de Lab, sans profils ni sessions partagés avec la production | E3 |
| `/opt/walter-profiles/{claude-code,codex,dsh}` (rendus de Soul) | `@instance/harness` (déjà prévu, vide aujourd'hui) | E9 |
| `/walter/router/serve/text_agent.py` (`walter_run`) | Absorbé par les sous-agents du moteur | E5 |
| `~/.hermes` (runtime Hermes) | Objet d'étude de Lab, isolé | E7 |

## 4. Composants mal placés (responsabilité ≠ module actuel)

Ils sont déclarés dans le registre avec leur `vision_target` ; ils se déplacent **avec** leur lot, pas avant.

| Composant | Aujourd'hui | Propriétaire cible | Lot |
|---|---|---|---|
| Serveur MCP, adaptateur de capacités, jeux d'outils | `core/server.py`, `walter_capabilities.py`, `config/toolsets.toml` | `core/interfaces/mcp` | E9 |
| Hook des runtimes | `core/hooks/walter_hook.py` | `core/interfaces/hooks` (Claude Code, Codex) ; le moteur ne l'appelle plus après E2 | E2, E9 |
| Greffons DSH, prise context DSH | `core/hooks/dsh`, `context/ports/dsh` | `core/engine/plugins` (intake, events, context) | E2 |
| Personnalisation web DSH | `core/ports/dsh-web-ui` | `core/interfaces/web` | E9 |
| Registre, contrats, chemins, instances | `core/walter_platform`, `core/modules` | `core/contracts` | E9 |
| Périmètres Computer Use | `core/modules/computer-policy.json` | `core/security` | E3 |
| Contrôle de divulgation | `memory/walter_memory/disclosure.py` | `core/security` (Memory reste fournisseur des classes de confidentialité) | E3 |
| Run Plane | `memory/walter_memory/runs.py` | `core/orchestration` (données inchangées, schéma `runs`) | E9 |
| Session navigateur du propriétaire | `core/browser_auth.py`, `core/browser_sites.json`, `core/bin/walter-browser` | `capabilities/browse` | E9 |
| Lanceur des gardiens | `core/bin/walter-guardians`, `core/ops/*.timer` | `ops/guardians` (chaque module garde son gardien) | E9 |
| Scénarios de bout en bout | `core/scenarios`, `walter-scenario` | `lab/scenarios` | E9 |
| Mise en veille | `core/walter_platform/standby.py` | `ops` | E9 |
| Alertes du Router qui reconfigurent Hermes | `router/analysis/alerts.py` | supprimées avec le rôle Hermes | E6 |
| Appels ponctuels Hermes | `router/serve/oneshot.py`, `media_exec.py` | Engine API, mode commande | E6 |

## 5. Hôte : chemins hors `/walter`

### 5.1 Commandes et liens

| Emplacement | Contenu | Cible | Remarque |
|---|---|---|---|
| `/usr/local/bin/walter*` (33 commandes) | liens vers les `bin/` des modules, souvent par `/opt/walter-*` | **noms publics conservés** ; les liens pointent directement sur le module déplacé | Interface publique : jamais renommée sans nécessité |
| `/usr/local/bin/kardex`, `vault`, `vault-sync`, `walter-browse` | liens vers `~/.hermes/bin/*` | `bin/` du module propriétaire (memory, browse), puis lien | Dépendance cachée à Hermes |
| `~/.hermes/bin/bw-unlock` | doublon de `secrets/bin/bw-unlock` | supprimé après preuve | Doublon |
| `/usr/local/sbin/walter-*-backup` | scripts de sauvegarde | `ops/backup/scripts` (déjà le cas pour une partie) | — |
| `/opt/walter-*` (14 liens) | compatibilité du 19/10 | conservés jusqu'à E9 ; retirés quand plus aucun appel n'y passe | Comptage des références avant retrait |
| `/srv/apps`, `/srv/projects`, `/root/projects/*` | liens de compatibilité | retirés après preuve | — |
| `/instances/monsieur` | lien → `/user/Lucas` | conservé tant qu'une configuration y renvoie | Le pointeur réel est `/etc/walter/instance` |
| `/etc/walter/` | pointeur d'instance, identités de navigation | inchangé (configuration de l'hôte) | — |

### 5.2 `~/.hermes` (22 Go)

| Élément | Rôle actuel | Cible |
|---|---|---|
| `hermes-agent/` (9,7 Go), `state.db` (5,3 Go), `profiles/`, `sessions/`, `checkpoints/` | Runtime Hermes et ses données | Hermes = objet d'étude de Lab après E7. **Données conservées** : déjà ingérées dans `walter_logs` et `core.events`, export brut dans le coffre chiffré |
| `plugins/walter-*` (7 copies installées) | ports Walter pour Hermes | retirés avec Hermes (E7) ; les sources restent dans les modules |
| `scripts/` (≈ 55 fichiers) | anciens scripts mémoire, bancs ; 18 scripts Hindsight/Qdrant mis en quarantaine le 09/11 (`/root/archive/2026/retired-hindsight-scripts-20261109/`) | classement par références (méthode de la skill d'audit), puis archive ; `memory_autopilot.py` est un **doublon** identique de `memory/ops/memory_autopilot.py` |
| `cron/` | 2 tâches restantes, en pause (AA Pareto, Kardex Semantic Extract) ; Memory Health Check, Memory Dreaming et Memory Importance Decay **retirées le 09/11** (Guardians) | — |
| `logs/` (858 Mo) | journaux de tous les services Walter (CLAUDE.md) | `@instance/logs` | **Fait le 11/11** (lien laissé) |
| `.env`, `google_token.json` | clés et jeton Google | Bitwarden et autorisations Secrets (E6) ; `camoufox-max` ne charge plus `.env` (11/11) ; restent : `walter-secrets-sync` (cible), `walter_memory/llm.py`, `walter-cloudflare` |
| `integrations/` (camoufox, codex, cloudflared, wrangler…) | outils tiers installés | **Fait le 11/11** : `/root/.codex`, `.gemini`, `.wrangler`, `.mcporter` (dossiers réels, liens inversés), cloudflared → `/services/cloudflared`, claude-code-router (vieille copie) en quarantaine |
| `camoufox-max`, `vault`, `raw-vault`, `walter-llm` | liens déjà repointés vers Browse et l'instance | retirés avec Hermes |

### 5.3 `/root` (hors outils de développement)

| Élément | Cible | Remarque |
|---|---|---|
| `CLAUDE.md`, `.claude/`, `.codex/` | inchangés | Outils externes de développement (arbitrage du 09/11) |
| `archive/` (6,1 Go) | *à valider* : quarantaine logicielle → `ops` ; fichiers personnels → `@instance/backups` | Mélange d'archives de logiciel et de travail |
| `reports/`, `scratch/`, `sessions/`, `work/` | `@instance/workspace` | Règle existante : pas de fichier en vrac dans `/root` |
| ~~`computer-use-v2-lot21/`~~ | — | **Retiré le 09/11** : aucune fonction de production n'en dépendait ; étude et banc conservés dans `lab/computer-use-v2` (à l'arrêt), unités archivées dans `/root/archive/2026/retired-computer-use-v2-shadow-20261109/` |
| `walter-computer-use/` (39 Mo) | à comparer avec `/walter/computer`, puis archive | Doublon probable |
| `webtop/` (1,7 Go de configuration) | `/services/webtop` | **Fait le 11/11** (lien laissé) |
| `.camoufox-max-data`, `.cloakbrowser-max-data` | `@instance/state/browse` | Profils de navigation = état de l'instance |
| `.agent-browser`, `.cua-driver`, `.copilot_shots`, `.cli-hub`, `.pxpipe`, `.hyperframes`, `.taste-skill`, `.grok`, `.fal`, `.tor`, `.claude-code-router`, `.dsh` | à classer un par un (outil, état d'un module, ou obsolète) | Aucun n'est déclaré dans un contrat |

### 5.4 `/opt` hors Walter

`/opt/scena-temp-storage` (service d'un projet) → `/projects/scena/…` ; `/opt/unified-monitoring-agent` et
`containerd` appartiennent à l'hôte Oracle et restent en place.

## 6. Documentation globale (`/walter/docs`)

| Document | Nature réelle | Cible |
|---|---|---|
| `VISION.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md` | global | restent (niveau 1) ; les sections de modules du RUNBOOK migrent vers le guide de chaque module |
| `STRUCTURE.md` | **structure de Walter Memory**, pas de Walter | `cognition/memory/docs` |
| `CONTEXT-ENGINE.md` | spécification de Context | `cognition/context/docs` |
| `PLAN.md` | plan de Walter Memory | `cognition/memory/docs` |
| `router_brain_v1_design.md` | conception du Router | `cognition/router/docs` |
| `HARNESS-CONTRACT.md`, `MODULARITY-2026-10-18.md` | modèle « compositions » remplacé par la vision | historique (`docs/history/`), avec renvoi |
| `SECRETS-HISTORY.md` | historique des expositions | `core/security/secrets/docs` |

## 7. Services externes (`/services`, créé le 09/11)

Arbitrage de Monsieur du 09/11 : `/services/` est le dossier des **dépendances opérationnelles** (bases de données,
bureaux distants, environnements Python partagés, passerelles). Leurs installations, définitions de déploiement et
données techniques y vivent ; le code, les contrats et les verrous de dépendances restent versionnés dans `/walter/`.
Un dossier par service, sans niveau intermédiaire : `/services/<service>/{compose.yaml|unité, config/, data/,
README.md}`. Aucune donnée n'est déplacée sans sauvegarde vérifiée, restauration essayée et place disque mesurée.
Composants déclarés dans le contrat d'Ops (`services`, `postgres`, `kernel-npm-cache`).

| Service | Aujourd'hui | Cible | État |
|---|---|---|---|
| PostgreSQL (`hindsight-pg`, :5433) | conteneur lancé à la main, volume Docker historique `hindsight-pg` (6,1 Go après le nettoyage phase 1 du 09/11 : objets Hindsight supprimés, `public` = extensions seules) | `/services/postgres/{compose.yaml,config/,data/,README.md}` ; nom du conteneur et port **conservés** (interface publique) ; **données sous `data/`**, le volume historique n'est pas gardé | **Définition préparée et essayée** sur une restauration complète du dump de la nuit (09/11) ; **données pas encore déplacées** : migration sur accord (procédure dans son README) |
| Cache hors ligne du noyau du moteur | — | `/services/dsh/npm-cache` | **Fait** (lot E1) |
| Environnements Python partagés | `/walter/runtime/venv`, venv de core, router, llm, raw-vault | `/services/python/<environnement>` | prévu (avec le déplacement de runtime) |
| Base d'essai (`walter-memory-testpg`, :5440) | conteneur d'essai (tmpfs 2 Go) | outillage de tests de Memory *à valider* | jetable |
| Webtop | conteneur ; config dans `/root/webtop` | `/services/webtop` | **Fait le 11/11** (compose + données ; `/root/webtop` = lien) |
| Bureau de navigation (`walter-browse-display`) | conteneur + unité | `/services/browse-display` (Browse consommateur) | **Fait le 11/11** (compose + `config/` ; volume anonyme remplacé) |
| Sortie WireGuard Freebox (`walter-wg-freebox-fr`) | conteneur lancé à la demande par `walter-wg-exit` (code et Dockerfile dans Browse) | **reste dans Browse** (11/11) : composant sans état construit depuis le code du module, pas une dépendance externe | — |
| Proxy NordVPN, FlareSolverr | conteneurs | `/services/nordvpn-proxy`, `/services/flaresolverr` | **Fait le 11/11** ; le proxy NordVPN est **cassé** (`sleep infinity`) : réparer ou retirer |
| Raw Vault S3 (`rclone serve s3`, :8899) | unité système | `/services/raw-vault-s3` (Memory consommateur) ; cache `/var/cache/raw-vault` | **Fait le 11/11** (source de l'unité ; clés lues dans l'instance) |
| Tunnel Cloudflare | unité + `~/.cloudflared` | `/services/cloudflared` | **Fait le 11/11** (`config/` ; `~/.cloudflared` = lien ; restes en quarantaine) |
| Ollama | unité inactive | à retirer après preuve (décision « pas de modèle local » du 03/11) | — |
| Applications (`aiostreams*`, excalidash, comfyui) | sous `/apps` | inchangé | l'étiquette compose d'excalidash désigne encore `/root/ExcaliDash`, dossier disparu |
| ~~Miroshark~~ et Neo4j | — | **retirés le 09/11** (arbitrage de Monsieur) : unités, application, Neo4j, tunnel Cloudflare et son DNS supprimés ; traces d'audit dans `@instance/backups/changes/2026-11-09-miroshark-retrait/` et `/root/archive/2026/retired-miroshark-20261109/` | — |

## 8. Instance (`/user/Lucas`)

| Vision | Aujourd'hui | Écart |
|---|---|---|
| `soul/`, `config/`, `accounts/`, `state/`, `workspace/`, `backups/`, `bootstrap/` | présents et utilisés | — |
| `profile/` | vide ; un `profiles/agent.md` existe à côté | doublon à résoudre (`profiles/` → `profile/`) |
| `skills/` | vide | skills propres à l'instance à définir avec Skills |
| `logs/` | journaux des services (depuis le 11/11, venus de `~/.hermes/logs`) | code qui écrit encore par le lien → E9.9 |
| `cache/` | vide | caches de modules à y rattacher quand ils sont propres à l'instance |
| — | `harness/` (vide), `instance.toml`, `README.md` | `harness/` recevra les profils rendus de Soul ; `instance.toml` est le manifeste de l'instance |

## 9. Systemd, gardiens, sauvegardes

- **106 fichiers d'unités** (système et utilisateur). Les unités Walter sont copiées dans `/etc/systemd/system`. Cible :
  chaque module livre ses unités dans son dossier (`systemd/` ou `ops/`), installées par `walter-ops` ; la commande
  lancée passe par le nom public, jamais par `/opt/walter-*`.
- **Unités historiques à classer** : `user-profile-compiler` (écrit `user_model` toutes les 5 min, voir le plan de
  nettoyage de Memory) et
  `walter-health-watchdog` (scripts Hermes), `hermes-desktop-*`, `gateway-watchdog`.
- **Secret dans un fichier d'unité** (relevé à E0) : `miroshark-tunnel.service` contenait le jeton du tunnel en
  clair. **Réglé le 09/11** : Miroshark retiré, tunnel Cloudflare supprimé (le jeton ne vaut plus rien).
- **Sauvegardes** : les chemins sauvegardés viennent des contrats (`backup_paths`), donc ils suivent les
  déplacements. restic, `walter-git-publish` et les essais de restauration doivent être relancés après chaque
  déplacement. `walter-git-publish` ne publie que ce qui est committé (voir le risque sur `secrets`).
- **Gardiens** : un par module, déclaré dans son contrat ; ils suivent leur module.

## 10. Doublons, restes et wrappers à faire disparaître (après preuve)

1. Seconde boucle agentique `walter_run` (E5) et passerelle d'outils `walter-tools` (E5).
2. Rôles de production de Hermes et ses 7 copies de greffons Walter (E6, E7).
3. `~/.hermes/scripts/memory_autopilot.py` (doublon). Scripts Hindsight et Qdrant : **en quarantaine depuis le 09/11** ; tables de Hindsight **supprimées le 09/11** (nettoyage phase 1).
4. Wrappers `~/.hermes/bin` (kardex, vault, vault-sync, walter-browse-doctor, bw-unlock).
5. `rawvault.py` (shim vers `walter_memory.objects`) et `secrets/compat`.
6. Liens `/opt/walter-*`, `/srv/*`, `/root/projects/*`, `/walter/backup`, `/walter/user` après la migration.
7. `/root/walter-computer-use` (probable ancienne copie de Computer).
8. Documents globaux qui décrivent un seul module (§ 6).

## 11. Points à faire trancher par Monsieur

1. Emplacement du journal d'exécution : `core/observability` (proposé) ou un autre nom.
2. Runtime Python partagé : environnements installés → `/services/python/` (**tranché le 09/11**) ; emplacement du
   code et des verrous : `ops/runtime` (proposé).
3. `/root/archive` : séparer quarantaine logicielle (`ops`) et archives personnelles (`@instance/backups`) ?
4. PostgreSQL : **tranché le 09/11** — données sous `/services/postgres/data/`, volume historique non gardé ;
   reste l'accord pour la fenêtre de migration, et la suppression de la base vide `stremio_app`.
5. Jeton en clair de `miroshark-tunnel` : **sans objet depuis le 09/11** (Miroshark retiré, tunnel supprimé).
