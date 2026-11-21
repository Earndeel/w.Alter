# Audit de l'existant — boucles d'exécution de Walter

| | |
|---|---|
| **Rôle** | État vérifié des boucles agentiques et de leurs dépendances avant la conception de `core/engine`. |
| **Propriétaire** | walter-core. |
| **Date** | 09/11/2026, relevés faits sur la VM (fichiers, composition effective `dsh --dump-config`, Postgres). |
| **Statut** | Constat. Ne décrit pas la cible (voir `02-ARCHITECTURE.md`). |

## 1. Vue d'ensemble

Aujourd'hui, trois boucles agentiques tournent pour W.Alter en production, plus les deux outils du builder :

| Boucle | Où | Qui l'utilise (14 derniers jours) | Statut cible |
|---|---|---|---|
| **DSH 0.2.0-rc.2** | `/opt/dsh` (paquet npm tel quel), `dsh-web.service`, interface :3080 | 97 runs de Monsieur + 111 runs d'essai | **Base du moteur unique** |
| **`walter_run`** (sous-agents texte) | `router/serve/run.py` + `text_agent.py` (170 lignes) | 23 tâches, la dernière le 28/10 | **Absorbée** dans le moteur |
| **Hermes** | `~/.hermes/hermes-agent` | 1 session Telegram, 6 `ask_hermes`, 16 lancées par le Router, 14 tâches planifiées, 9 bureau | **Sort de la production**, devient un sujet d'étude de Lab |
| Claude Code, Codex | outils du builder | 38 et 118 sessions | Outils externes de développement, branchés par MCP (décision du 09/11) |

Le moteur unique n'a donc pas à être inventé : DSH en fait déjà l'essentiel. Le travail consiste à le figer, à y
ramener la délégation, à retirer à Hermes ses rôles de production et à rendre natif ce qui passe encore par des
scripts de hook.

## 2. Boucle 1 — DSH (DeepSeek Harness)

### 2.1 Ce qu'est DSH

- 289 paquets `@deepseek-ai/*` en version 0.2.0-rc.2. Ils sont sous licence MIT, sauf `libreoffice-kit` (MPL-2.0,
  aperçu de documents) et `node-addon-system` (BSD-3). Ils font environ 620 000 lignes de JavaScript compilé, dont
  173 000 rien que pour l'aperçu de documents, et 524 Mo sur le disque. Node 22.
- **Cordis** : un cadre de greffons avec injection de dépendances, services à portée, nettoyage géré par le cycle de
  vie et chargement par configuration. Chaque fonction de DSH est un greffon identifié (`id`). Une composition peut en
  désactiver un, le remplacer ou en insérer un autre. **C'est le mécanisme de stratégies interchangeables dont Walter
  a besoin, déjà présent.**
- Le code source vit sur GitHub (`deepseek-ai/deepseek-harness`, monorepo). Il est installé ici sous forme compilée.
- Chaque paquet a un README normalisé : résumé, implémentation, expérience du modèle, limites connues. C'est le
  même esprit que la règle documentaire de Monsieur.

### 2.2 Les fonctions de DSH qui couvrent les besoins du moteur

| Besoin (demande du 09/11) | Paquet DSH | Ce qu'il garantit | Limites relevées dans son README |
|---|---|---|---|
| Sessions persistantes | `dsh-session` + `dsh-session-persistence-jsonl` | Journal de session append-only, historique du modèle dérivé du journal, relecture, embranchement | Embranchement simple seulement, pas d'arbre de sessions |
| Reprise après incident | `dsh-session-checkpoint-policy` | Point durable avant chaque appel de modèle, avant chaque outil à effet et avant l'étape suivante | Pas d'« exactement une fois » : un appel sans résultat est noté « issue inconnue », jamais rejoué. Pas de point durable au milieu d'une réponse du modèle |
| Boucle et outils | `dsh-agent-loop`, `dsh-agent`, `dsh-tools` | Tours, étapes, flux, outils en parallèle quand c'est sûr, reprise d'une session par `sessionId` stable | **Pas de budget de tour intégré** : il faut l'arrêter par `agent/turn-stopping` |
| Sous-agents | `dsh-subagent` (+ `-fork/-spawn-in-process`, ACP, Codex, Claude Code) | Enfants nommés, résultats collectés, enfants continuables | Résidence locale au processus, pas de boîte aux lettres durable vers le parent, un message accepté puis perdu au crash n'est pas rejoué |
| Interruptions | `dsh-agent` (annuler, orienter), `dsh-user-questions` | Annulation, orientation en cours de tour, question à l'utilisateur | Petite fenêtre d'attente pendant l'annulation |
| Permissions | `dsh-sandbox-policy`, `dsh-user-approval`, `dsh-permission-presets` | Bac à sable unique pour shell, fichiers et terminal ; approbation ponctuelle avant une action sensible ; échec fermé sans répondant | Accords ponctuels seulement (pas d'« autoriser toujours ») ; la demande ne montre pas les arguments de l'outil ; pas d'approbation hors tour |
| Tâches longues | `dsh-jobs` | Tâches de fond avec identifiant, sortie, attente, annulation | — |
| Rappels planifiés | `dsh-schedule` | Rappels ponctuels, quotidiens, cron, livrés dans leur session, survivent au redémarrage | L'hôte doit tourner ; livraison au moins une fois, pas exactement une fois |
| Événements extérieurs | `dsh-webhook` | Règles qui ouvrent une session sur un événement de confiance | — |
| Portes d'entrée | `dsh-api-gateway` + contrôleurs (web), `dsh-sdk-jsonrpc-server` (SDK stdio), `dsh-acp` (ACP), `dsh-headless` | Un même moteur servi au web, au SDK, à l'ACP et en mode commande | SDK : un processus par client ; changement de configuration = redémarrage |
| Appels de modèle | `dsh-llm` + `dsh-llm-pi-ai` (bibliothèque **pi-ai** du projet Pi, `@earendil-works/pi-ai` 0.87) | Fournisseurs multiples, passerelles compatibles OpenAI | Une seule invite système en tête |
| Compaction | `dsh-compaction` (contrat) | Résumé de l'historique ancien, suite intacte | — |
| Hooks | `dsh-hooks-claude-code` | Exécute des hooks au format Claude Code : bloquer, ajouter du contexte, relancer un tour | **Ni `SessionEnd` ni `PreCompact`** |

### 2.3 Comment Walter l'adapte aujourd'hui (sans toucher au code amont)

Le fichier `cordis.patch.yml` est généré par `walter harness install dsh`. Il pose deux sections gérées, dans
`profiles/web` et `profiles/headless`, et protège chaque ligne Walter par une empreinte.

- **Modèles** : fournisseur `walter`, qui pointe sur `walter-llm` :8894. Le modèle `auto` suit le ContextPlan du
  message, lu par walter-llm sur le run.
- **Contexte** : `/walter/context/ports/dsh/index.mjs`, 168 lignes. Il branche le moteur de compaction de
  walter-context sur le moteur de compaction public de DSH, et la compaction de base est désactivée.
- **Message du propriétaire** : `/walter/core/hooks/dsh/owner-turn.mjs`, 35 lignes. Il ne garde que ce que Monsieur a
  écrit, sans les avis du runtime.
- **Visage W.Alter** : `/walter/core/ports/dsh-web-ui`, extension serveur et navigateur, interface en français.
- **Outils Walter** : client MCP vers `/opt/walter-core/server.py`, avec le jeu d'outils `core` (16 outils plus
  `walter_call`).
- **Hooks** : `walter-hooks.json` lance `walter_hook.py` à `SessionStart`, `UserPromptSubmit`, `Stop` et
  `PostToolUse(bash)`. Le script fait le preflight, le contexte, les skills, le run, le journal et les événements du bus.
- **Désactivé**, parce que Walter le possède : identité et persona DeepSeek, skills DSH, web DSH, recherche DSH,
  orchestration native (goal, plan, **sous-agents**, workflow, ralph, todo), comptes et télémétrie DeepSeek, choix du
  modèle dans l'interface.
- **Gardé** : boucle, sessions JSONL et points de reprise, bac à sable shell et fichiers, approbations, tâches de
  fond, terminal, pièces jointes, titres de session (par la tâche Router `summarization`).

### 2.4 Écarts relevés dans la boucle DSH

1. **Version non figée** : `package.json` demande `^0.2.0-rc.2`, hors git. Une réinstallation peut changer le moteur.
2. **Preflight, run et événements par processus shell** : chaque message lance `walter_hook.py`, un processus Python.
   Le moteur ne connaît le plan que par effet de bord (walter-llm le lit sur le run).
3. **Pas de garde de divulgation** : Claude Code a un `PreToolUse` sur les outils qui envoient des messages
   (`disclosure_hook.py`), Hermes un `pre_tool_call`. DSH n'en a pas.
4. **Pas de `SessionEnd`** : la fin de session dépend de l'observateur de journaux (limite déclarée dans
   `compositions/dsh.json`).
5. **Pas de budget de tour** : rien n'arrête un tour qui s'emballe, sauf le quota.
6. **Sous-agents natifs coupés** : la délégation passe par l'outil MCP `walter_run`, donc par une seconde boucle
   (§ 3), au lieu des enfants du moteur.
7. **Index de recherche de sessions** (`dsh-session-query-sqlite`) chargé mais inerte (`:memory:`, `openAt: never`).
   Il serait un second index des sessions s'il était activé. walter_logs couvre déjà la recherche.
8. **Télémétrie produit** (`dsh-host-product-telemetry-otel`, `dsh-client-product-analytics`) : présente, mais elle
   n'est active que dans le profil `desktop`, inutilisé. Rien ne sort aujourd'hui. À désactiver explicitement au gel.
9. **Environnement de test partagé** : `/opt/dsh/test-home` partage `profiles/` et `sessions/` avec la production par
   des liens (incident du 07/11). Les essais doivent utiliser une copie isolée (`stage-home`).

## 3. Boucle 2 — `walter_run` (sous-agents texte du Router)

### 3.1 Chemin actuel

```
outil MCP walter_run (ou outil Hermes, ou `walter-router run`)
 └─ processus walter-router run
     ├─ décision du Router : intent.classify (2ᵉ décision d'intention, sans la conversation)
     ├─ processus walter-context-child : dossier de départ par recette fixe (mémoire toujours, 3 skills sans seuil)
     ├─ processus walter-tools serve : passerelle vers les outils MCP walter (liste blanche, liste NEVER)
     └─ text_agent.run : boucle (max_turns ≤ 120, budget ≤ 3 600 s)
          ├─ à chaque tour : processus walter-llm call (exact_call, une route, sans cache Codex)
          ├─ outils de base : terminal (bash, shell=True), read_file, write_file
          └─ outils Walter par la passerelle
     → runs.task_start/task_end, runs.trace (session walter_logs propre), observations dans Memory
```

Les mesures du 08/11 (`/root/reports/2026-11-08-walter-run-sous-agent-plan.md`) donnent 13,5 s pour « 95 % de 23 »,
dont environ 2,3 s utiles, et 40 s pour la météo, dont environ 16 s utiles.

### 3.2 Ce qui a de la valeur

- **Repli entre fournisseurs sans perdre la conversation**, déjà fait aussi par la passerelle walter-llm sur le
  chemin HTTP.
- **Traçabilité** : une tâche par délégation dans le Run Plane, trace complète dans walter_logs, coûts dans
  `models.exec_log`.
- **Contrat de sortie** : sortie JSON vérifiée par `walter-scenario`, sources issues d'une lecture Browse réelle.
- **Observations persistées** dans Memory après le run.
- **Liste NEVER** de la passerelle : pas de récursion `walter_run`, pas de secret, pas d'écriture dans les skills ou
  le coffre, pas de contrôle du Mac, pas de `memory_retain`.

### 3.3 Ce qui pose problème

- **C'est une seconde boucle de production**, contraire à la vision (§ 9, « un seul runtime »).
- **Pas de session persistante, pas de reprise, pas d'interruption** autre que le budget, pas d'approbation.
- **Le terminal n'a pas de bac à sable** (`subprocess.Popen(..., shell=True)`) : un sous-agent peut écrire partout
  avec les droits root. C'est un écart de sécurité. **Corrigé le 09/11** (router `64b1b48`) : terminal retiré, fichiers confinés au
  dossier du run (`03-MIGRATION.md` § S0).
- **Les décisions sont refaites** : `intent.classify` au lieu du ContextPlan, recette de contexte au lieu du plan.
- **Un processus neuf à chaque étape** (walter-router, walter-context-child, walter-tools, walter-llm call).

## 4. Boucle 3 — Hermes, ce qu'il fait encore en production

| Rôle | Où | Remplacement prévu |
|---|---|---|
| Passerelle Telegram (bot principal) et retour des clics sur les propositions du Router | `hermes-gateway` (unité utilisateur), greffon `walter-router` | `core/interfaces/telegram` sur le moteur (H4) |
| Réponses ponctuelles L1 du Router (recommandations, veille des abonnements) | `router/serve/oneshot.py` → `hermes chat --oneshot` | Moteur en mode commande (session sans interface) ou appel direct à walter-llm |
| Préparation des invites médias | `router/serve/media_exec.py` → `hermes chat --oneshot` | Idem |
| Alertes du Router qui modifient la config Hermes et redémarrent sa passerelle | `router/analysis/alerts.py`, `serve/hermes_sync.py` | Le branchement Hermes devient facultatif (Lab) ; le moteur lit la configuration du Router sans synchronisation |
| Jeton Google le plus large (Drive, envoi de mails, agenda en écriture) | `~/.hermes/google_token.json` (colab, `ask_hermes`) | Autorisation dans `walter_secrets.grants` (déclarée le 19/10, pas reprise) |
| Tâches planifiées | `~/.hermes/cron/jobs.json` : « Memory Health Check » (5 min), « Memory Dreaming » (04:00) | Le contrôle de santé passe aux guardians et à systemd (Ops fonctionne sans modèle) ; **Dreaming est mort** depuis le retrait de Hindsight (19/10) : échec complet le 09/11, un appel de modèle payé chaque nuit ; **mise en pause le 09/11** |
| Délégation `ask_hermes` (comptes Google, agenda, navigateur) | outil MCP walter-core | Outils du moteur adossés aux autorisations Walter ; `ask_hermes` reste comme voie d'étude, hors production |
| Application Hermes Desktop sur le Mac (profil `wild`) | `hermes-desktop-backend` | Hors périmètre du moteur ; à décider avec Monsieur au lot de parité (H6) |

Les autres liens avec Hermes ne sont pas des dépendances de production : la lecture de `state.db` par Memory (une
source parmi d'autres) et les greffons qui branchent Hermes sur les modules (entre 10 et 400 lignes chacun).

**Chemins `~/.hermes` en dur dans le code de modules neutres** (à remplacer par la résolution de l'instance) :
- memory : `llm.py`, `context.py` (`memories/USER.md`), `objects.py`, `purge.py`, `hygiene.py` ;
- core : `server.py`, `hooks/walter_hook.py` (journal du hook), `browser_auth.py`,
  `walter_platform/composition.py` et `harness.py` ;
- browse : moteurs Camoufox et CloakBrowser installés dans `~/.hermes/camoufox-max` ;
- colab : dossier temporaire, jeton Google.

## 5. Ce que Walter possède déjà et que le moteur doit utiliser sans le refaire

| Mécanisme | Où | Usage par le moteur |
|---|---|---|
| Preflight (plan de chaque message, voie sans modèle) | walter-context, service :8897 (`/preflight`) | Seule décision d'intention. Appel direct depuis le moteur, plus par un hook shell |
| ContextPlan v2, SessionState v1, ThreadHint v1 | `context/contracts/schemas/` | Contrats d'entrée du tour |
| ChildContextSpec v1, `walter-context-child` | walter-context | Dossier de départ d'un sous-agent, à servir par le service déjà démarré |
| Compaction (`compress`) | walter-context, prise DSH | Seul moteur de compaction |
| Passerelle de modèles | `cognition/router/llm` (aujourd'hui `/walter/router/llm`, :8894) | Seul accès aux modèles : abonnements d'abord, replis, coûts, cache |
| Run Plane (`runs.runs`, `tasks`, `links`, `episodes`) | `walter_memory/runs.py` | Registre canonique des runs et tâches : le moteur y écrit, il n'en crée pas d'autre |
| Bus Walter | `walter_memory/bus.py` (Postgres LISTEN/NOTIFY) | Événements `turn.ended`, `session.ended`, `run.*` |
| walter_logs | `walter_memory/logs.py`, `walter-logs-watch` | Journal brut d'exécution. Il relève de l'observabilité du Core (décision du 09/11), Memory le consomme |
| Outils MCP walter, jeux d'outils par client | `core/server.py`, `config/toolsets.toml` | Surface d'outils Walter du moteur |
| Politique Computer Use, liste NEVER, autorisations (`grants`), garde de divulgation | core, secrets, memory | Politique de sécurité unique, appliquée par le moteur |
| Soul | walter-soul, `/opt/walter-profiles/dsh/AGENTS.md` | Identité du moteur |
| Banc | `walter-scenario`, `walter matrix`, banc stage DSH, `context/bench/levels.py` | Tests de non-régression et comparaisons Lab |
| Registre des modules et présentation (M0/M1/guide/index) | `contracts/*.json` → `modules/registry.json`, `manifest/` | Documentation et découverte du moteur |

## 6. Verdict : garder, adapter, supprimer

| Élément | Verdict | Raison |
|---|---|---|
| Noyau DSH/Cordis (boucle, sessions, points de reprise, sous-agents, tâches, approbations, bac à sable, portes, rappels, webhook) | **Garder**, figé | Couvre tous les besoins ; MIT ; points d'extension publics |
| Composition `walter harness install dsh` et sections gérées | **Garder**, déplacer vers `core/engine/compositions` | Mécanisme d'adaptation déjà éprouvé |
| `owner-turn.mjs`, prise contexte, `dsh-web-ui` | **Garder** | Greffons Walter conformes ; chacun reste chez son propriétaire (core ou context) |
| `walter_hook.py` pour le moteur | **Adapter** : preflight, run et événements deviennent des greffons natifs ; le hook reste pour Claude Code et Codex | Évite un processus par message ; le moteur connaît son plan |
| Sous-agents natifs DSH | **Réactiver** sous stratégie Walter (contexte, modèle, budget, liste NEVER) | Remplace la boucle `walter_run` |
| `walter_run` (outil) | **Adapter** : porte d'entrée vers une délégation du moteur | Même nom d'outil pour tous les appelants |
| `text_agent.py` (boucle) | **Supprimer** après le lot E5 (quarantaine) | Seconde boucle ; terminal sans bac à sable |
| `walter-tools serve` | **Supprimer** quand `text_agent` part (le moteur a un client MCP natif) | Ne sert qu'à la boucle `walter_run` |
| `intent.classify` pour le texte | **Réduire** aux médias et au secours | Le preflight décide |
| Lancements de Hermes par le Router | **Supprimer** | Rôle de production de Hermes |
| Tâche « Memory Dreaming » | **Supprimer** (sa cible n'existe plus) | Morte, payante |
| `dsh-session-query-sqlite`, télémétrie produit | **Désactiver** explicitement au gel | Second index potentiel ; rien ne doit pouvoir sortir |
| JSONL de sessions du moteur | **Garder** comme stockage de travail du moteur (comme `state.db` pour Hermes) ; walter_logs reste le journal | Nécessaire aux points de reprise. Un stockage direct dans Postgres sera étudié par Lab (lot E8), et adopté seulement s'il est mesuré meilleur |
