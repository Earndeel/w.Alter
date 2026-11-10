# Plan de convergence E0 → E9 : runtime unique et architecture de la vision

| | |
|---|---|
| **Rôle** | Ordonner la convergence de Walter vers `VISION.md`, lot par lot, avec tests, critères d'adoption et retour arrière essayé. Deux objectifs menés ensemble : **A** convergence fonctionnelle (un seul runtime de production) et **B** convergence architecturale (arborescence, conventions, interfaces, documentation). |
| **Propriétaire** | walter-core (exécution : le builder ; validation : Monsieur, **lot par lot**). |
| **État** | 09/11/2026 · direction validée par Monsieur. **S0 et E0 faits** (§ S0, § E0). **E1 autorisé le 09/11 et en cours** (§ E1 : gel fait et prouvé, compositions rendues depuis une source, rattrapage documentaire fait ; restent 48 h de service inchangé, jusqu'au 11/11 au soir). Chaque lot suivant est autorisé séparément. Lots hors moteur ouverts le 09/11 : E9.2 PostgreSQL (préparé, § E9) et nettoyage de Memory (plan à valider, § M). |
| **Ne fait pas** | Ne décrit pas l'organisation interne du moteur (`02-ARCHITECTURE.md`) ni l'inventaire des emplacements (`05-CARTOGRAPHIE.md`). |
| **Contrats** | Schémas du moteur `core/engine/contracts/` ; registre des modules (`vision_target` des modules et des composants) ; règle documentaire `/walter/docs/DOCUMENTATION.md`. |

## Règles communes à tous les lots

1. **Un lot = un changement réversible, une responsabilité.** Aucun déplacement massif ni changement simultané de
   plusieurs responsabilités sans nécessité démontrée. Avant chaque lot : étiquette git `engine-E<n>-avant` dans les
   dépôts touchés, sauvegarde des fichiers d'état dans `@instance/backups/changes/<date>-engine-E<n>/`.
2. **Chaque lot déclare** : composants et chemins ; changements de comportement ; interfaces et dépendances touchées ;
   tests et scénarios ; impacts sur les données et la sécurité ; documentation modifiée ; conditions d'adoption ;
   retour arrière **essayé une fois avant l'adoption**, pas seulement écrit.
3. **Aucun nouveau chemin de production sans les garanties de sécurité** (§ Sécurité) : permissions et
   approbations, bac à sable, contrôle de ce qui sort vers des tiers (fournisseurs de modèles compris), périmètres
   par porte, utilisateur et sous-agent, isolation des sessions, échec fermé. Un retour arrière ne réactive jamais une
   voie dangereuse.
4. **Placement** : le code, les adaptations et les contrats Walter naissent à leur place définitive. Les modules
   existants ne sont déplacés qu'au lot E9, module par module. Les artefacts compilés ou reconstruisibles (paquets
   installés, caches) ne sont ni versionnés ni déplacés sans besoin ; ils sont décrits par un verrou et des
   empreintes.
5. **Une seule source de vérité** : Run Plane pour les runs et tâches, walter_logs pour l'observabilité, bus Walter
   pour les événements, Memory pour la consolidation, registre pour les modules et composants. Aucun second bus,
   journal, registre de sessions métier ou système de mémoire. Événements et opérations à effet idempotents.
6. **Ombre sans effet** : un mode d'observation n'écrit jamais dans les données métier ni sur le bus de production
   (événements `observation=true`, comparaison écrite par Lab).
7. **Tests minimaux de chaque lot**, en plus des siens : tests des modules touchés ; `walter check` (contrats,
   frontières, neutralité, documentation) ; `walter-scenario` sur la composition web ; banc `levels.py` (plancher
   mesuré le 09/11 : rappel 16/18, 0 fuite) ; `walter status`, `walter-memory health`, `memory-autopilot` si Memory
   est touchée ; comparaison avec `04-BASELINE.md`.
8. **Budget** : bancs sur fournisseurs payants plafonnés à 2 €/24 h ; au-delà, accord de Monsieur.
9. **Documentation** : un lot n'est fini que si les README, les contrats et `DECISIONS.md` décrivent le nouvel état.

## Sécurité : où chaque garantie est livrée

| Garantie demandée | Aujourd'hui (09/11) | Livrée et vérifiée au lot |
|---|---|---|
| Bac à sable des commandes et fichiers | Noyau DSH : bac à sable unique. `walter_run` : **terminal retiré, fichiers confinés au dossier du run** (S0) | E1 (gel du bac à sable du noyau), E3 (politique), E5 (commande des sous-agents seulement dans ce bac à sable) |
| Permissions et approbations avant une action sensible | Approbation ponctuelle du noyau, web seulement | E3 (politique Walter, refus prioritaire), E7 (boutons Telegram) |
| Contrôle de ce qui sort vers des tiers, fournisseurs de modèles compris | Garde de divulgation (Claude Code, Hermes) ; règle de confidentialité du 03/11 (identifiants masqués) appliquée par Memory | E3 : décision de politique pour `outgoing_message` **et** `model_call` (classe de données vs fournisseur), sans changer la règle de Monsieur |
| Périmètres par porte, utilisateur et sous-agent | Périmètres Computer Use par interface | E3 (presets par porte et principal), E5 (enfant ≤ parent moins NEVER, profondeur ≤ 3) |
| Isolation des sessions, propagation contrôlée des droits | Le banc d'essai DSH partage profils et sessions avec la production | E3 (test-home isolé), E5 (droits propagés explicitement) |
| Échec fermé sans autorisation | Noyau : oui sur le web | E3 (sans répondant ⇒ refus, contrat `policy-decision.v1`) |

E4, E5 et E7 ouvrent de nouveaux chemins de production : ils ne sont **activés** qu'après l'adoption de E3.

## Vue d'ensemble

| Lot | Objet | A / B | Change la production ? | Dépend de |
|---|---|---|---|---|
| **S0** | Corrections urgentes : terminal de `walter_run`, Memory Dreaming | sécurité | Oui (fait le 09/11) | — |
| **E0** | Contrats, registre enrichi, mesures, cartographie, règle documentaire | A + B | Non (fait) | — |
| **E1** | Gel technique du noyau (sans déplacement) ; rattrapage documentaire | A + B | Non (même code, même place) — en cours | E0 |
| **E2** | Accueil et événements natifs | A | Oui, après ombre — construit et essayé hors service (10/11), ombre après adoption d'E1 | E1 |
| **E3** | Politique, approbations, divulgation, budget | A (sécurité) | Oui | E2 |
| **E4** | Engine API v1 | A + B (`core/interfaces`) | Ajout, activé après E3 | E2, E3 |
| **E5** | `walter_run` devient une délégation du moteur | A | Oui, avec repli | E3, E4 |
| **E6** | Fin des rôles de production de Hermes (hors Telegram) | A | Oui | E4 |
| **E7** | Telegram sur le moteur ; Hermes passe à Lab | A + B | Oui, après une semaine en parallèle | E3, E4 |
| **E8** | Reprise après incident éprouvée | A | Non (essais) puis peut-être | E2 |
| **E9** | Migration physique de l'arborescence, module par module | B | Oui (liens de compatibilité) | E7 pour core ; avant pour les sous-lots indépendants |
| **M** | Grand nettoyage de Walter Memory (hors moteur, phase par phase) | B (données) | Oui, données | sauvegarde complète et archive pérenne (phase 0) |

E4 et E8 peuvent être préparés en parallèle de E3. Les sous-lots E9 qui ne touchent pas au moteur (§ E9) peuvent être
proposés plus tôt, chacun avec son propre accord. **Walter n'est pas terminé à E8** : la convergence s'achève quand
E9 est fait et qu'aucun lien de compatibilité, wrapper ou système concurrent ne reste (§ Fin).

## S0 — Corrections urgentes (faites le 09/11)

| | Terminal non sandboxé de `walter_run` | Memory Dreaming (Hermes) |
|---|---|---|
| Composants | `router/serve/text_agent.py`, `router/serve/run.py` | tâche `13d0f88771cb` de `~/.hermes/cron/jobs.json` |
| Comportement | Jeux `terminal` et `code_execution` refusés (`toolset_disabled`, avant tout lancement) ; `read_file`/`write_file` confinés au dossier privé du run (liens symboliques et chemins absolus refusés) ; jeux par défaut inchangés (`walter-web`, `skills`, `memory`) ; interrupteur `WALTER_RUN_TOOLS` supprimé | Tâche en pause, historique conservé ; Memory Health Check inchangé |
| Preuve d'innocuité | 0 appel terminal ou fichier sur les 23 tâches du Run Plane | Cible (Hindsight) retirée le 19/10 ; échec chaque nuit, un appel de modèle payé |
| Tests | router 343 réussis ; essai réel : `walter-router run` avec `terminal` ⇒ refus | état `paused` vérifié |
| Retour arrière | **Aucun retour vers le terminal.** Une régression des outils fichiers se corrige en avant ; l'étiquette `security-walter-run-terminal-avant` sert à l'audit | Réactivation par Hermes ou copie `jobs.json.before` (sauvegarde du 09/11), seulement sur décision de Monsieur |
| Commit | router `64b1b48` | — (fichier d'état de Hermes) |

## E0 — Contrats, registre, référence (fait le 09/11)

- **Composants et chemins** : `core/engine/contracts/` (6 schémas : Engine API v1, accueil, Délégation v1, Décision
  de politique v1, événement du moteur, stratégie) ; `core/engine/tests/` ; `components` et `vision_target` dans les
  17 contrats et le catalogue ; `walter_platform/documentation.py` ; `/walter/docs/DOCUMENTATION.md` ;
  `04-BASELINE.md`, `05-CARTOGRAPHIE.md`.
- **Comportement** : aucun. `walter layout` affiche la cible de la vision ; `walter check` ajoute le contrôle
  documentaire en avertissement.
- **Interfaces touchées** : schéma des contrats de modules (`components`, `vision_target`), registre compilé,
  `docs/contracts.generated.md`.
- **Tests** : 13 tests de schémas (exemples valides et invalides, ContextPlan v2 réutilisé par référence) ; tests du
  registre, des composants et du contrôle documentaire ; `walter contracts check`, `walter check`.
- **Données et sécurité** : aucune donnée touchée ; contrats sans valeur de l'instance (neutralité vérifiée).
- **Retour arrière** : revert des commits (documentation, schémas, contrôles en lecture seule) ; étiquette
  `engine-E0-avant` dans core.

## E1 — Gel technique du noyau

Le gel et le déplacement physique sont séparés : **E1 gèle, sans rien déplacer.**

- **Composants et chemins** : `core/engine/kernel/` (source Walter : verrou de version exacte, `package-lock`,
  empreintes d'intégrité, script d'installation reproductible, README). L'installation reste dans `/opt/dsh`. Le cache
  hors ligne est rangé hors git, à un emplacement d'Ops déclaré dans le contrat. `core/engine/compositions/` : source
  des compositions web et headless, rendues par walter-core comme aujourd'hui (`walter harness install dsh`).
- **Comportement** : aucun. Même code, même place, même unité `dsh-web.service` (le nom de l'unité ne change qu'à E9).
- **Interfaces et dépendances** : aucune interface publique ne change ; `walter-ops` gagne la vérification des
  empreintes de l'installation.
- **Tests** : réinstallation complète depuis le cache hors ligne dans un dossier d'essai, empreintes identiques ;
  `--dump-config` identique avant et après le rendu des compositions ; scénario web ; session existante reprise.
- **Données et sécurité** : sessions non touchées ; le bac à sable du noyau est gelé tel quel et sa configuration est
  vérifiée par empreinte.
- **Documentation** : README de `kernel/` et `compositions/` ; rattrapage du stock documentaire (13 en-têtes, README
  de colab et raw-vault), puis contrôle documentaire en blocage.
- **Adoption** : réinstallation depuis le cache réussie deux fois, 48 h de service inchangé, `walter check` en
  blocage vert.
- **Retour arrière indépendant** : une archive de l'installation actuelle, faite avant E1 et vérifiée par empreinte,
  se restaure sans le cache ni le nouveau script ; essai de restauration dans un dossier d'essai avant l'adoption.

**Avancement au 09/11 (soir)** — fait et prouvé :

- `core/engine/kernel/` : version exacte (`0.2.0-rc.2`, sans plage), verrou complet régénéré sans changer un seul
  paquet, `installed.json` (empreinte par paquet installé, des 6 fichiers de composition et de la configuration
  composée `--dump-config` des profils web et headless, déterministe à deux exécutions), `verify.py`, `install.sh`.
- Cache hors ligne dans `/services/dsh/npm-cache` (Ops, arbitrage `/services` du 09/11).
- Réinstallation complète hors ligne **deux fois** dans un dossier d'essai : 0 paquet manquant, en trop ou différent.
- Retour arrière : archive `tar.zst` de l'installation en service (`@instance/backups/changes/2026-11-09-engine-E1/`,
  empreinte SHA-256), restaurée par `tar` seul dans un dossier d'essai : conforme.
- `walter engine kernel` (lecture seule, sortie 1 en cas d'écart) ; la vigie d'Ops lève `engine_kernel_drift` (G3,
  jamais d'action automatique) ; composant `engine-kernel` déclaré dans `contracts/core.json`.

Fait le 09/11 (soir) — compositions rendues depuis une source (`core/engine/compositions/`, README) :

- Tout était déjà rendu par walter-core sauf la « face » du profil web (ligne `connection` : connexion d'un an ;
  `walter-ui` : nom et accueil de l'instance) et deux retouches de la racine (noms affichés des modèles, rétention
  longue du cache de prompt). Gabarit neutre `dsh-face.patch.yml` + valeurs `@instance/config/core/engine.toml`
  (défaut neutre `core/config/engine.toml`) → bloc géré `dsh-face`, placé avant `dsh-web` ; noms des modèles et
  rétention du cache dans la définition du fournisseur. Une ligne écrite à la main pour les mêmes cibles est un
  conflit explicite (jamais une seconde copie).
- Adoption en service : les deux lignes tenues à la main retirées seulement après vérification qu'elles égalaient le
  rendu, puis `walter harness install dsh --apply` (transaction sauvegardée). **`--dump-config` identique avant et
  après** (web et headless, empreintes du manifeste), rendu idempotent, `dsh-web` non redémarré et toujours actif ;
  répété d'abord sur une copie. Seule l'empreinte de `profiles/web/cordis.patch.yml` change dans `installed.json`.
- Reproduction depuis un dossier vide : configuration composée identique à l'installation en service, sauf les
  préférences d'interface que DSH enregistre lui-même (thème, langue, avis d'accueil) et un reste inerte dans une
  ligne désactivée (`skill-filesystem`).
- Retour arrière : `@instance/backups/changes/2026-11-09-engine-E1-compositions/` (fichiers d'avant + empreintes,
  code d'avant, manifeste d'avant, transaction du rendu, script d'adoption).

Reste à faire dans E1 : 48 h de service inchangé (jusqu'au 11/11 au soir), avec `walter engine kernel` conforme, puis adoption.

Fait le 09/11 (fin d'après-midi) : rattrapage documentaire (13 en-têtes standard, README de colab et du Raw Vault ;
`walter check` : 0 constat, contrôle documentaire passé en blocage) et environnement de test de core (`core/bin/walter-core-test` : pytest de
`walter-python` + paquet `mcp` du venv de core, rien d'installé ; 223 tests verts).

## E2 — Accueil et événements natifs

- **Composants** : `core/engine/plugins/intake`, `core/engine/plugins/events` ; routes `/v1/runs/*` et
  `/v1/bus/emit` de la passerelle Memory (**lot Memory**, validé dans son principe, le Run Plane et le bus restent les
  seules sources).
- **Comportement** : le moteur n'appelle plus `walter_hook.py` par message ; le preflight est appelé directement ;
  `session.ended` émis nativement. `walter_hook.py` reste pour Claude Code et Codex.
- **Interfaces** : ContextPlan v2 inchangé ; identifiant de session stable par porte (`web/…`).
- **Tests** : même ContextPlan pour un même message (0 écart d'intention et de niveau) ; un run par tour ; clés
  d'idempotence (un même tour rejoué n'ouvre pas un second run) ; voie sans modèle sans appel de modèle ; latence.
- **Données et sécurité** : ombre d'une semaine avec événements `observation=true`, jamais écrits sur le bus de
  production ni dans `runs` ; la comparaison est écrite par Lab.
- **Adoption** : zéro écart d'intention sur la semaine, latence égale ou meilleure (référence 04-BASELINE § 2).
- **Retour arrière** : interrupteur `intake=hook` de la composition, redémarrage ; essayé pendant l'ombre.

**État (10/11/2026) : construit et essayé hors service ; l'ombre démarre après l'adoption d'E1.** Fait :
- greffons `core/engine/plugins/intake` et `events` (README du dossier) ; interrupteur `[dsh.engine] intake =
  "hook" | "shadow" | "native"` rendu par `walter harness install dsh` (en service : `hook`, composition identique à
  l'octet) ; en `native`, `walter-hooks.json` perd `UserPromptSubmit` et `Stop` (gardés : `SessionStart`,
  `PostToolUse`) et le greffon `walter-owner-turn` part (l'accueil lit lui-même le texte du propriétaire) ;
- lot Memory : routes `POST /v1/runs/start`, `/v1/runs/end`, `/v1/bus/emit` (types `turn.started`, `turn.ended`,
  `session.ended` seulement ; toute charge `observation` refusée), `/v1/privacy/classify`, et `cloud_safe` sur
  `/v1/context` ; le guetteur `walter-logs-watch` lance l'ingestion `agent-sessions --dsh` quand les fichiers du moteur
  changent (avant : seulement le crochet `Stop`) ;
- tests : 9 tests Node des greffons, bascule hook → shadow → native → hook de la composition, 8 tests des routes ;
  suites complètes core 244 et Memory 332 vertes ;
- essai réel (`bench/e2_intake.py`, DSH headless, foyers de test `/opt/dsh/e2-home` natif et `/opt/dsh/e2-hook-home`
  crochet, mêmes messages en alternance, canal `test`) : voir le tableau ci-dessous.

| 15 tours par mode (3 passages × 5 messages) | `native` (greffons) | `hook` (`walter_hook.py`) |
|---|---|---|
| Accueil du tour, p50 / p90 / max | 1,68 s / 2,68 s / 4,2 s | 2,16 s / 2,80 s / 3,6 s |
| Fin de tour (crochet `Stop`), p50 | 0 (asynchrone, hors du tour) | 0,80 s |
| Durée totale du tour, p50 / moyenne | 9,2 s / 8,8 s | 10,4 s / 9,9 s |
| Réponses obtenues | 15/15 | 15/15 |
| Runs par tour / `turn.ended` par tour | 1 / 1 partout | 1 / 1 partout |
| Plan (niveau, acte, tâche) | mêmes valeurs ; les deux seuls écarts (tâche `coding`/`general` sur un message, acte `continue`/`new` sur un autre) apparaissent **dans les deux modes** pour le même texte : échantillonnage du modèle de décision, pas l'accueil | idem |

Écarts assumés (DECISIONS 2026-11-10, lot E2) : la clé de session reste `dsh/vm/<id>` (continuité de walter_logs,
core.events, runs et skills) — l'identifiant par porte (`web/…`) arrive avec l'Engine API (E4) ; un écart d'intention
ne compte contre l'accueil que si le texte du propriétaire diffère, le preflight échantillonnant son modèle de décision
(même texte, plans parfois différents : bruit mesuré à part, à traiter dans Context).

Reste : adoption d'E1 (11/11 au soir) → `intake = "shadow"` sur le service (une semaine, `bench/e2_shadow.py`), essai
du retour arrière pendant l'ombre → `native` si zéro écart imputable à l'accueil, couverture complète et latence au
moins égale ; `endOnDispose` décidé d'après ce que l'ombre montre des déchargements d'agents.

## E3 — Politique, approbations, divulgation, budget

- **Composants** : `core/security` (politique, presets par porte et principal ; reprend `modules/computer-policy.json`
  et la garde de divulgation, Memory restant fournisseur des classes de confidentialité) ;
  `core/engine/plugins/policy`, `core/engine/plugins/budget`.
- **Comportement** : décision `allow | ask | deny` avant chaque outil, chaque message sortant et chaque appel de
  modèle ; refus prioritaire ; sans répondant ⇒ refus. Banc d'essai isolé des profils et sessions de production.
- **Prérequis Context** : le ContextPlan v2 **n'a pas de champ d'effort**. Le budget de tour attend une extension
  possédée par Context (lot Context séparé, accord de Monsieur) ; d'ici là, le greffon budget n'applique que les
  plafonds fixes de la composition.
- **Tests** : jeu d'essais de politique (message vers un tiers sans accord bloqué ; Computer hors périmètre refusé ;
  secret jamais rendu ; appel de modèle d'une classe interdite au fournisseur refusé ; approbation absente ⇒ refus ;
  enfant qui demande plus que son parent refusé) ; usages web ordinaires inchangés.
- **Données et sécurité** : décisions écrites dans le Run Plane et walter_logs, arguments sensibles masqués.
- **Adoption** : tous les cas passent ; aucune demande d'approbation superflue sur une semaine d'usage web.
- **Retour arrière** : retrait du greffon de la composition ; le bac à sable et l'approbation du noyau restent (jamais
  moins protégé qu'aujourd'hui).

## E4 — Engine API v1

- **Composants** : `core/interfaces/api` (greffon hôte : jeton d'agent 0600, flux SSE, port déclaré dans le registre) ;
  mode commande.
- **Comportement** : ajout seulement ; activé après E3, chaque appel passe la politique de sa porte.
- **Tests** : tests de contrat de chaque opération (`engine-api.v1`) ; ouverture, reprise, annulation, file,
  approbation ; 20 sessions simultanées sans fuite ; refus sans jeton.
- **Adoption** : contrats verts, mémoire vive stable sur 72 h (référence `dsh-web` 209 Mo).
- **Retour arrière** : retrait du greffon hôte ; rien n'en dépend encore.

## E5 — `walter_run` devient une délégation du moteur

Ce lot reprend et remplace les lots A–D du plan du 08/11.

- **Composants** : `core/orchestration` (stratégie de sous-agents) ; outil natif `walter_run` ; l'outil MCP
  `walter_run` appelle l'opération `delegate` (`delegation.v1`).
- **Comportement** : sous-agents du noyau sous stratégie Walter (ChildContextSpec, plan réutilisé ou demandé une
  fois, droits ≤ parent moins NEVER, profondeur ≤ 3, budget). La commande n'existe que dans le bac à sable du noyau.
  `text_agent.py` reste derrière un interrupteur de repli deux semaines (sans terminal), puis quarantaine avec
  `walter-tools serve`. La préparation d'invite des médias cesse d'appeler Hermes.
- **Tests** : scénarios `walter_run` existants rejoués ; aucun `shell=True` hors bac à sable ; enfants annulés avec
  leur parent ; coûts et `task_id` dans le Run Plane ; observations persistées dans Memory.
- **Adoption** : parité de réussite sur les scénarios et une semaine d'usage réel (peu d'usage depuis le 28/10 : un
  jeu de scénarios est construit avant), coût par mission égal ou moindre.
- **Retour arrière** : interrupteur `walter_run.engine=false` ⇒ ancienne boucle **sans terminal** ; ensuite
  restauration depuis la quarantaine.

## E6 — Fin des rôles de production de Hermes (hors Telegram)

- **Composants** : `router/serve/oneshot.py`, `media_exec.py`, `router/analysis/alerts.py` → mode commande de
  l'Engine API ; autorisation Google → grants de Secrets ; Memory Health Check → gardiens.
- **Comportement** : plus aucun appel `hermes …` hors Lab ; la tâche Memory Dreaming (en pause) part en quarantaine.
- **Tests** : tests du Router ; une proposition Telegram du Router produite sans Hermes ; recherche de tout appel
  `hermes` restant.
- **Adoption** : un cycle de 48 h du Router sans Hermes.
- **Retour arrière** : par fonction, interrupteur qui revient à l'appel Hermes (Hermes reste installé jusqu'à E7).

## E7 — Telegram sur le moteur

- **Composants** : `core/interfaces/telegram` (session `telegram/<chat>`, `/stop`, boutons d'approbation, pièces
  jointes, voix par le STT du Router).
- **Comportement** : une semaine en parallèle (second bot ou conversation d'essai), puis bascule. Hermes devient objet
  d'étude de Lab ; sa passerelle est arrêtée, pas supprimée. Ses données restent (déjà dans walter_logs et
  `core.events`).
- **Tests** : liste de parité tirée des usages réels (agrégats walter_logs) ; reprise après redémarrage ; approbation
  par bouton ; conversation retrouvée par Memory.
- **Adoption** : liste de parité complète et accord explicite de Monsieur.
- **Retour arrière** : `hermes gateway start` sur le bot principal (jeton inchangé), arrêt de l'interface.

## E8 — Reprise après incident

- **Fait** : essais de panne (arrêt pendant un appel de modèle, un outil à effet, un enfant ; passerelle Memory
  coupée ; disque plein simulé) ; « issue inconnue » et `engine.recovered` vérifiés. En Lab seulement : stockage des
  sessions dans Postgres au vocabulaire walter_logs, adopté seulement si mesuré meilleur.
- **Tests** : chaque panne finit avec un run fermé, aucun outil rejoué en double, la session reprise.
- **Adoption** : tous les scénarios passent deux fois de suite.
- **Retour arrière** : sans objet pour les essais ; retour au JSONL par la composition.

## E9 — Migration physique de l'arborescence

Conçue dès E0 (`05-CARTOGRAPHIE.md`, `vision_target` dans le registre), exécutée **module par module**, chaque
sous-lot autorisé séparément et déclaré avec les mêmes champs que les autres lots.

**Pour chaque déplacement** : inventaire des références (code, imports, scripts, unités systemd, CLI, MCP,
configurations, contrats, gardiens, sauvegardes, skills, `walter_logs` sur 30 jours) ; déplacement ; mise à jour de
ces références ; lien de compatibilité vérifié ; tests du module et `walter check` ; services redémarrés verts ;
sauvegarde restic puis **essai de restauration** ; documentation. Noms publics (commandes, ports, outils MCP,
événements, conteneurs) conservés.

| Ordre proposé | Sous-lot | Risque |
|---|---|---|
| E9.1 | Documents globaux propres à un module → leur module (aucun code) | faible |
| E9.2 | `/services/<service>` : dépendances opérationnelles (arbitrage du 09/11). **PostgreSQL d'abord, données déplacées sous `/services/postgres/data/`** (le volume Docker historique n'est pas gardé). Préparé le 09/11 : définition, essai de restauration et de démarrage (voir ci-dessous) ; migration sur accord. Puis environnements Python partagés (`/services/python/`), Webtop, conteneurs de Browse | moyen |
| E9.3 | `capabilities/` : skills, browse (avec la session navigateur de core), computer, colab | moyen |
| E9.4 | `cognition/` : context ; router avec llm ; memory avec vault | élevé (Memory : sauvegarde PG et essai de restauration avant) |
| E9.5 | Extraction de `core/bus` et du journal d'exécution hors de Memory (bibliothèques, schémas PG inchangés) | moyen |
| E9.6 | Éclatement de core : `interfaces/mcp`, `interfaces/hooks`, `contracts`, `security` (avec secrets), `identity` (soul), gardiens vers ops, scénarios vers Lab | élevé (après E7) |
| E9.7 | Instance : `logs`, `profile`, `harness`, profils de navigation ; dossiers en vrac de `/root` | moyen |
| E9.8 | Restes de `~/.hermes` (scripts, wrappers, greffons) et doublons, après preuve de non-usage | faible |
| E9.9 | Retrait des liens de compatibilité, quand plus aucun appel n'y passe | faible, en dernier |

- **Retour arrière** : par sous-lot, lien inversé et restauration des unités et configurations sauvegardées ; essayé
  sur le premier sous-lot de chaque famille.

### E9.2 PostgreSQL — préparé le 09/11, données pas encore déplacées

- **Composants** : `/services/postgres/{compose.yaml, config/, README.md}` (contrat d'Ops, composant `postgres`) ;
  image verrouillée par empreinte ; configuration complète dans `config/` (y compris `hba_file` et `ident_file`).
- **Essais faits** : restauration complète du dump de la nuit dans un PostgreSQL jetable (`pg_restore` sans erreur ;
  562 958 événements = exactement ceux présents dans la base au moment du dump ; extensions identiques) ; démarrage de
  la définition sur cette copie : `healthy`, configuration lue depuis `config/`, connexion TCP par le port publié
  depuis la passerelle Docker comme les clients. L'essai a corrigé un défaut : sans `hba_file`, PostgreSQL lisait les
  règles d'accès restées dans les données.
- **Place disque** : déplacement dans le même système de fichiers (`mv`, instantané, sans copie) ; 26 Go libres le
  09/11 au soir.
- **Procédure, vérifications et retour arrière** : README du service. Interface publique inchangée (conteneur
  `hindsight-pg`, `127.0.0.1:5433`). Coupure de 2 à 5 minutes.
- **Limite relevée** : le dump nocturne ne contient pas les rôles du serveur (`pg_dump` d'une base) ; une
  restauration sur un serveur neuf doit recréer le rôle `hindsight`. Ajout d'un export des rôles à la sauvegarde
  nocturne proposé (phase 0 du lot M).

## M — Grand nettoyage de Walter Memory (plan à valider)

Demande de Monsieur du 09/11. Audit et plan : `/walter/memory/docs/NETTOYAGE-2026-11.md` (volumes par schéma,
classement mémoire personnelle / connaissances du projet / observabilité / artefacts techniques, dépendances, phases
0 à 6, gains estimés). **Rien n'est supprimé** : chaque phase est autorisée séparément ; la phase 0 (archive
pérenne des connaissances et sauvegarde complète restaurable) précède toute suppression. Ordre recommandé : M avant
la migration des données de E9.2 (moins de données à déplacer et à sauvegarder), mais les deux sont indépendants.

## Fin de la convergence

Walter est conforme à la vision quand : un seul runtime de production (`walter layout` : 17/17 cibles atteintes) ;
aucune référence à `/opt/walter-*`, `/srv/*`, `~/.hermes` hors Lab ; aucun wrapper ou doublon de la liste
`05-CARTOGRAPHIE.md` § 10 ; `walter check` en blocage vert ; chaque module, composant et dossier annexe
auto-descriptif.

## Prérequis et risques résiduels (relevés avant E1, mis à jour le 09/11 au soir)

| # | Sujet | État au 09/11 | Traitement proposé |
|---|---|---|---|
| 1 | Disque | 9,5 Go libres (94 %) le matin ; **26 Go libres le soir** (retrait de Miroshark et Neo4j, nettoyages) | Réglé pour E1 (archive 101 Mo, cache 141 Mo) ; le nettoyage de Memory (lot M) en rendra davantage |
| 2 | Stock documentaire | 13 en-têtes incomplets, README absents pour colab et raw-vault | **Réglé le 09/11** : en-têtes et README faits, 0 constat ; `walter check` en blocage |
| 3 | Tests MCP de core | 18 tests sans interpréteur commun (paquet `mcp` + pytest) | **Réglé le 09/11** : `core/bin/walter-core-test`, 223 tests verts |
| 4 | Dépôt `secrets` | Travail non committé du 25/10 au 07/11, déjà compilé dans le registre ; non publié par `walter-git-publish` | Monsieur ou l'agent auteur le committe ; le contrat `secrets.json` modifié par E0 attend ce commit |
| 5 | Tests de browse | 5 échecs antérieurs au 09/11 | À corriger dans un lot Browse séparé |
| 6 | Coûts | 2 572 appels sur 2 588 au coût inconnu (abonnements) | Imputer le coût des abonnements au prix de revient du Router avant le budget de E3 |
| 7 | Effort | Absent du ContextPlan v2 | Extension possédée par Context, lot séparé |
| 8 | Jeton en clair | `miroshark-tunnel.service` (désactivée) lisible par tous | **Réglé le 09/11** : Miroshark retiré, tunnel supprimé (jeton sans valeur) |
| 9 | Service hors registre | `computer-use-v2-shadow` tournait depuis `/root/computer-use-v2-lot21` et lisait `state.db` | **Réglé le 09/11** : arrêté et retiré, étude conservée dans `lab/computer-use-v2` |
| 10 | Rappel du contexte | 16/18 (17/18 le 07/11) ; preflight qui sous-estime le niveau dans 9 cas sur 29 | Sujet de Context ; plancher des lots fixé à 16/18 |
| 11 | Noyau préliminaire | DSH 0.2.0-rc.2 | Gel exact (E1), mise à jour seulement par Lab |
| 12 | Délai du journal Hermes | p95 de 135,7 s | Sans effet sur le moteur ; disparaît avec E7 |

## Ce que Monsieur valide maintenant

Réglé le 09/11 : E0 accepté, E1 autorisé (en cours), données PostgreSQL sous `/services/postgres/data/`, runtime
Python installé sous `/services/python/`, jeton de `miroshark-tunnel` (Miroshark retiré). Restent :

1. Le plan de nettoyage de Memory (lot M), phase par phase, à commencer par la phase 0.
2. La fenêtre de migration des données PostgreSQL (E9.2, coupure de 2 à 5 minutes), de préférence après les phases
   1 à 4 du lot M.
3. La suppression de la base vide `stremio_app` (base, rôle, règles d'accès ouvertes à toute adresse).
4. Les points encore ouverts de `05-CARTOGRAPHIE.md` § 11 (nom du dossier du journal, emplacement du code de runtime,
   `/root/archive`).
