# Cartographie : arborescence actuelle → architecture cible

| | |
|---|---|
| **Rôle** | Établir, pour chaque emplacement actuel de Walter, son emplacement cible de la vision, ses dépendances et ce qui doit disparaître. Base de la convergence architecturale (objectif B) et du lot E9. |
| **Propriétaire** | walter-core (exécution des déplacements : walter-ops, un module à la fois). |
| **État** | Inventaire relevé le **09/11/2026** sur la VM. **Rien n'est déplacé.** Les cibles marquées *à valider* attendent une décision de Monsieur. |
| **Ne fait pas** | Ne remplace pas le catalogue des modules : pour les 17 modules et leurs 78 composants, la source est `core/modules/catalog.json` (`vision_target`) et les contrats (`components[].vision_target`), visibles par `walter layout` et `docs/contracts.generated.md`. Ce document couvre ce que le registre ne décrit pas (hôte, services, instance, dossiers annexes) et explique les déplacements. |
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
| runtime (Python partagé) | `/walter/runtime` | `/walter/ops/runtime` *à valider* | — | Absent de la vision ; c'est de l'installation, donc Ops |
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
| `scripts/` (≈ 60 fichiers) | anciens scripts mémoire, Hindsight, bancs | classement par références (méthode de la skill d'audit), puis archive ; `memory_autopilot.py` est un **doublon** identique de `memory/ops/memory_autopilot.py` |
| `cron/` | 2 tâches actives avant le 09/11 ; **Memory Dreaming en pause depuis le 09/11** ; Memory Health Check (5 min) | Health Check → gardiens (E6) |
| `logs/` (848 Mo) | journaux de tous les services Walter (CLAUDE.md) | `@instance/logs` (vide aujourd'hui) | 
| `.env`, `google_token.json` | clés et jeton Google | Bitwarden et autorisations Secrets (E6) |
| `integrations/` (camoufox, codex, cloudflared, wrangler…) | outils tiers installés | `/apps` ou outils de l'hôte, selon l'usage |
| `camoufox-max`, `vault`, `raw-vault`, `walter-llm` | liens déjà repointés vers Browse et l'instance | retirés avec Hermes |

### 5.3 `/root` (hors outils de développement)

| Élément | Cible | Remarque |
|---|---|---|
| `CLAUDE.md`, `.claude/`, `.codex/` | inchangés | Outils externes de développement (arbitrage du 09/11) |
| `archive/` (6,1 Go) | *à valider* : quarantaine logicielle → `ops` ; fichiers personnels → `@instance/backups` | Mélange d'archives de logiciel et de travail |
| `reports/`, `scratch/`, `sessions/`, `work/` | `@instance/workspace` | Règle existante : pas de fichier en vrac dans `/root` |
| `computer-use-v2-lot21/` | `capabilities/computer` ou Lab | **Un service d'ombre tourne depuis ce dossier** (`computer-use-v2-shadow`) |
| `walter-computer-use/` (39 Mo) | à comparer avec `/walter/computer`, puis archive | Doublon probable |
| `webtop/` (1,7 Go de configuration) | `/services/webtop` | § 7 |
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

## 7. Services externes (`/services`, à créer)

`/services/<service>/` = définition de déploiement (compose, unité), configuration, et données persistantes **quand
c'est pertinent**. Les données ne sont jamais déplacées sans sauvegarde vérifiée et essai de restauration.

| Service | Aujourd'hui | Cible | Données |
|---|---|---|---|
| PostgreSQL (`hindsight-pg`, :5433) | conteneur lancé à la main, volume Docker `hindsight-pg` | `/services/postgres` (compose + config) ; nom du conteneur et port **conservés** (interface publique) | Volume Docker conservé ; déplacement des données seulement si mesuré utile, avec essai de restauration complet |
| Base d'essai (`walter-memory-testpg`, :5440) | conteneur d'essai | `/services/postgres-test` ou outillage de tests de Memory *à valider* | jetable |
| Webtop | conteneur ; config dans `/root/webtop` | `/services/webtop` | `config/` déplacée avec le service |
| Bureau de navigation (`walter-browse-display`) | conteneur + unité | `/services/browse-display` (Browse consommateur) | volume Docker |
| Sortie WireGuard Freebox (`walter-wg-freebox-fr`) | conteneur | `/services/wg-exit` (Browse consommateur) | — |
| Proxy NordVPN, FlareSolverr | conteneurs | `/services/nordvpn-proxy`, `/services/flaresolverr` | — |
| Raw Vault S3 (`rclone serve s3`, :8899) | unité système | `/services/raw-vault-s3` (Memory consommateur) | cache `/var/cache/raw-vault` |
| Tunnel Cloudflare | unité + `~/.cloudflared` | `/services/cloudflared` | — |
| Ollama | unité inactive | à retirer après preuve (décision « pas de modèle local » du 03/11) | — |
| Applications (`aiostreams*`, excalidash, comfyui, miroshark) | déjà sous `/apps` | inchangé | l'étiquette compose d'excalidash désigne encore `/root/ExcaliDash`, dossier disparu |

## 8. Instance (`/user/Lucas`)

| Vision | Aujourd'hui | Écart |
|---|---|---|
| `soul/`, `config/`, `accounts/`, `state/`, `workspace/`, `backups/`, `bootstrap/` | présents et utilisés | — |
| `profile/` | vide ; un `profiles/agent.md` existe à côté | doublon à résoudre (`profiles/` → `profile/`) |
| `skills/` | vide | skills propres à l'instance à définir avec Skills |
| `logs/` | vide ; les journaux sont dans `~/.hermes/logs` | migration des journaux (rotation `logrotate` incluse) |
| `cache/` | vide | caches de modules à y rattacher quand ils sont propres à l'instance |
| — | `harness/` (vide), `instance.toml`, `README.md` | `harness/` recevra les profils rendus de Soul ; `instance.toml` est le manifeste de l'instance |

## 9. Systemd, gardiens, sauvegardes

- **106 fichiers d'unités** (système et utilisateur). Les unités Walter sont copiées dans `/etc/systemd/system`. Cible :
  chaque module livre ses unités dans son dossier (`systemd/` ou `ops/`), installées par `walter-ops` ; la commande
  lancée passe par le nom public, jamais par `/opt/walter-*`.
- **Unités historiques à classer** : `computer-use-v2-shadow` (dossier en vrac), `user-profile-compiler` et
  `walter-health-watchdog` (scripts Hermes), `hermes-desktop-*`, `gateway-watchdog`.
- **Secret dans un fichier d'unité** : `miroshark-tunnel.service` (désactivée) contient le jeton du tunnel en clair,
  lisible par tous les comptes de la machine. Correction proposée : jeton dans un fichier 0600 ou dans Bitwarden,
  jeton à faire tourner. **Hors du mandat du 09/11 : en attente de l'accord de Monsieur.**
- **Sauvegardes** : les chemins sauvegardés viennent des contrats (`backup_paths`), donc ils suivent les
  déplacements. restic, `walter-git-publish` et les essais de restauration doivent être relancés après chaque
  déplacement. `walter-git-publish` ne publie que ce qui est committé (voir le risque sur `secrets`).
- **Gardiens** : un par module, déclaré dans son contrat ; ils suivent leur module.

## 10. Doublons, restes et wrappers à faire disparaître (après preuve)

1. Seconde boucle agentique `walter_run` (E5) et passerelle d'outils `walter-tools` (E5).
2. Rôles de production de Hermes et ses 7 copies de greffons Walter (E6, E7).
3. `~/.hermes/scripts/memory_autopilot.py` (doublon), scripts Hindsight et Qdrant retirés (archive).
4. Wrappers `~/.hermes/bin` (kardex, vault, vault-sync, walter-browse-doctor, bw-unlock).
5. `rawvault.py` (shim vers `walter_memory.objects`) et `secrets/compat`.
6. Liens `/opt/walter-*`, `/srv/*`, `/root/projects/*`, `/walter/backup`, `/walter/user` après la migration.
7. `/root/walter-computer-use` (probable ancienne copie de Computer).
8. Documents globaux qui décrivent un seul module (§ 6).

## 11. Points à faire trancher par Monsieur

1. Emplacement du journal d'exécution : `core/observability` (proposé) ou un autre nom.
2. Runtime Python partagé : `ops/runtime` (proposé).
3. `/root/archive` : séparer quarantaine logicielle (`ops`) et archives personnelles (`@instance/backups`) ?
4. PostgreSQL : définition sous `/services/postgres` avec données dans le volume Docker actuel (proposé), ou
   déplacement des données.
5. Jeton en clair de `miroshark-tunnel` : le corriger et le faire tourner.
