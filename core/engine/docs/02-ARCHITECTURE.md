# Architecture cible de `core/engine`

| | |
|---|---|
| **Rôle** | Décrire l'organisation interne du runtime unique, ses contrats, ses stratégies interchangeables et son branchement aux autres modules. |
| **Propriétaire** | walter-core. |
| **Date / statut** | 09/11/2026 · **brouillon à valider par Monsieur**. Les contrats ci-dessous deviennent des schémas JSON au lot E0. |
| **Sources** | `VISION.md` (§ 4, 8, 9), arbitrages de Monsieur du 09/11 (`DECISIONS.md`), audit `01-AUDIT.md`. |

## 1. Principe

**Le moteur Walter est la base DSH/Cordis figée, composée de greffons Walter.** On ne réécrit pas une boucle, on n'en
garde pas deux : on fige celle qui fait déjà presque tout, on la compose depuis Walter et on y ramène ce qui
tournait à côté (`walter_run`, rôles de Hermes).

Trois couches :

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ core/interfaces    web (:3080) · Engine API (local) · MCP · Telegram · commande │  portes d'entrée,
│                    · rappels · webhooks                                          │  aucune boucle
├───────────────────────────────────────────────────────────────────────────────┤
│ core/engine/plugins   greffons Walter, un par point d'extension :              │  stratégies
│   intake · context · model · tools · orchestration · policy · budget ·         │  interchangeables
│   events · recovery · identity                                                  │
├───────────────────────────────────────────────────────────────────────────────┤
│ core/engine/kernel    DSH/Cordis figé : boucle, sessions + points de reprise,   │  noyau, code amont
│   sous-agents, tâches, approbations, bac à sable, rappels, webhook, portes     │  non modifié
└───────────────────────────────────────────────────────────────────────────────┘
        │ appelle par interfaces déclarées, ne refait aucune décision
        ▼
 Context (preflight, ContextPlan, contexte, compaction) · Router (choix + passerelle de modèles)
 · Memory (Run Plane, core.events, vues) · Soul · Skills / Browse / Computer / Colab (MCP walter)
 · Secrets (autorisations) · observabilité du Core (walter_logs, bus)
```

- **Noyau** : les paquets DSH aux versions exactes de la production (0.2.0-rc.2), avec leurs empreintes et un cache
  hors ligne. Toute mise à jour passe par Lab (banc, comparaison, accord de Monsieur) puis par un nouveau gel.
- **Greffons Walter** : chacun remplace ou complète un greffon du noyau par son identifiant Cordis. Le comportement
  vient de Walter, la mécanique du noyau.
- **Compositions** : une composition par usage (web, API, commande, essai Lab), générée par walter-core comme
  aujourd'hui (`walter harness install dsh`), avec sections gérées et empreintes. Une variante Lab n'est qu'une autre
  composition, pas un autre moteur.

## 2. Un seul processus hôte, plusieurs portes

```
 Monsieur (web)    Telegram        Claude Code / Codex      Router, Ops        événement (tri, webhook)
      │               │                 │ (MCP walter_run)      │ (commande)          │
      ▼               ▼                 ▼                       ▼                     ▼
 dsh web app    interfaces/telegram   core/server.py ──────► Engine API v1 ◄──── interfaces/events
      │               │                                         │
      └───────────────┴──────────────► walter-engine.service ◄──┘   (un seul hôte Cordis :
                                       sessions · tours · enfants      web + API + rappels)
```

- **Un hôte** (`walter-engine.service`, successeur de `dsh-web.service`) sert l'interface web, l'Engine API, les
  rappels et les webhooks. Toutes les sessions vivent dans le même moteur et le même stockage de sessions.
- **Engine API v1** : porte locale de Walter (127.0.0.1, jeton d'agent comme pour :8890 et :8894, flux
  d'événements). Elle est implémentée par un greffon hôte au-dessus des services publics du noyau (`ctx.agents`,
  contrôleur de sessions). Les interfaces ne parlent que ce contrat, jamais le protocole interne de DSH. C'est ce
  qui permettra un jour de changer de noyau sans toucher aux portes.
- **Mode commande** (une tâche, une réponse) : une session sans interface passée par l'Engine API. Elle remplace
  `hermes chat --oneshot` pour le Router, et `dsh --profile headless` pour les essais.
- **MCP** : `core/server.py` reste la surface d'outils pour Claude Code et Codex. Leur `walter_run` devient un appel
  à l'Engine API ; ces clients restent des outils externes de développement.

## 3. Points d'extension et stratégies interchangeables

Chaque point d'extension a **une stratégie par défaut** en production. Les autres stratégies vivent dans Lab, sous
forme de compositions variantes, et ne sont adoptées qu'après banc, tests de non-régression et accord de Monsieur.

| Point d'extension | Responsabilité | Stratégie par défaut | Alternatives que Lab peut comparer |
|---|---|---|---|
| **intake** | Accueillir un message : garder le texte du propriétaire, ouvrir le run, obtenir **le** ContextPlan, servir la voie sans modèle | `owner-turn` (existe) + appel direct au preflight :8897 ; le run s'ouvre par la passerelle Memory | — (décision unique, par principe) |
| **context** | Injecter le contexte selon le plan, compacter sans perte silencieuse | prise walter-context (existe) : pack ou legacy selon `inject.json` ; compaction `compress` | `dsh-compaction-basic`, élagage DSH des résultats d'outils, idées Hermes |
| **model** | Exécuter un appel de modèle | `dsh-llm-pi-ai` → fournisseur `walter` (walter-llm), modèle `auto` = plan ; aucun choix dans le moteur | transport HTTP direct ; autres adaptateurs pi-ai — toujours derrière la passerelle du Router |
| **tools** | Outils de base et outils Walter | DSH : bash, fichiers, recherche de fichiers, tâches, question, présentation ; Walter : MCP walter, jeu `core` + `walter_call` | présentation progressive (lot 3) contre liste complète ; parallélisme des appels |
| **orchestration** | Sous-agents et missions | sous-agents en processus du noyau, réactivés sous stratégie Walter (§ 5.3) | enfants ACP, enfants Codex ou Claude Code (développement seulement) |
| **policy** | Décider avant chaque outil : autoriser, demander, refuser | bac à sable DSH + approbation DSH + greffon Walter (divulgation, périmètres Computer, liste NEVER, autorisations) | « auto review » expérimental de DSH, règles mémorisées |
| **budget** | Arrêter un tour au bon moment | greffon sur `agent/turn-stopping`, alimenté par le **contrat d'effort** du ContextPlan (consultation / standard / approfondi) | budgets fixes, budgets appris |
| **events** | Publier ce qui se passe | greffon natif → bus (`turn.ended`, `session.ended`, `run.*`, `approval.*`, `delegation.*`) + Run Plane | — |
| **persistence** | Stocker les sessions pour la reprise | JSONL du noyau avec points de reprise ; walter_logs alimenté par `walter-logs-watch` | stockage direct dans Postgres en vocabulaire walter_logs (lot E8, si mesuré meilleur) |
| **identity** | Instructions du moteur | rendu Soul (`/opt/walter-profiles/dsh/AGENTS.md`) | — |

Règle commune : **un point d'extension, une stratégie active, une responsabilité.** Une stratégie ne peut pas
prendre une décision qui appartient à un autre module : le choix du modèle reste au Router, l'intention au preflight,
le contenu du contexte à Context.

## 4. Contrats

Ces contrats sont possédés par core et rangés dans `core/engine/contracts/` (schémas JSON au lot E0). Ils réutilisent
les contrats existants au lieu de les recopier.

### 4.1 Engine API v1 (interfaces → moteur)

| Opération | Entrée | Sortie / effet |
|---|---|---|
| `session.open` | `interface`, `conversation` (identifiant propre à la porte), `principal` (propriétaire ou machine), `mode` (`interactive` / `command`), `permissions` (preset nommé) | `session_id` stable `<interface>/<compte>/<conversation>` ; reprise si elle existe |
| `turn.submit` | `session_id`, `message` (texte + pièces jointes), `channel` (`owner` / `machine` / `test`), `overrides` facultatifs (`task`, `level`, `model` choisis explicitement) | `run_id` ; réponse immédiate si voie sans modèle ; sinon flux d'événements |
| `turn.steer` / `turn.queue` | `session_id`, `message` | message injecté dans le tour en cours, ou mis en file |
| `turn.cancel` | `session_id`, `reason` | annulation du tour et de ses enfants ; `run.ended(cancelled)` |
| `approval.answer` | `request_id`, `decision` (`allow_once` / `deny`), `principal` | débloque ou refuse l'action en attente |
| `delegate` | contrat Délégation v1 (§ 4.3) | résultat de l'enfant, ou suivi si long |
| `events.subscribe` | `session_id` ou `run_id` | flux du vocabulaire § 4.5 |
| `health` | — | état du noyau, de la composition, des dépendances |

Transport : HTTP local avec jeton d'agent (fichier 0600 de l'instance) et flux SSE. Jamais de secret dans l'URL.

### 4.2 Accueil d'un tour (intake → reste du moteur)

Entrée : le message du propriétaire, isolé des avis du runtime par `owner-turn`. Étapes :
1. `runs.start` par la passerelle Memory (une seule source pour les runs) ;
2. `POST /preflight` (walter-context :8897) → **ContextPlan v2** (`context/contracts/schemas/context-plan.v2.json`),
   écrit sur le run (`runs.routing.requested`, comme au lot 2 du 07/11) ;
3. si le plan porte une réponse sans modèle (heure, date, calcul sûr), elle est rendue et le tour s'arrête ;
4. sinon le plan fixe le contexte (prise context), le niveau et la tâche du modèle (walter-llm lit le plan du run),
   les outils présentés et le contrat d'effort (budget).

Un tour = un plan. Les étapes suivantes du même tour (appels d'outils) ne redemandent pas de plan.

### 4.3 Délégation v1 (moteur ou porte → sous-agent)

Il reprend les champs actuels de `walter_run` pour que l'outil garde son nom et sa forme : `goal`, `toolsets`,
`budget_seconds`, `max_turns`, `task` / `level` / `model` explicites, `output_contract`, `run_id` parent.

- Si le but délégué est le message du propriétaire, **le plan du run est réutilisé**. Pour un sous-but différent, le
  preflight produit un plan pour ce but, avec le plan parent en contexte. C'est une seule décision, jamais
  `intent.classify` pour le texte.
- Le dossier de départ est un ChildContextSpec v1, servi par le service walter-context déjà démarré, selon le plan.
- Les droits de l'enfant sont au plus ceux du parent, moins la liste NEVER : pas de récursion illimitée, pas de
  secret, pas d'écriture dans les skills ou le coffre, pas de contrôle du Mac sans périmètre.
- Résultat : sortie (validée par le contrat de sortie s'il y en a un), sources, coûts, `task_id` du Run Plane.
  Observations persistées dans Memory comme aujourd'hui.

### 4.4 Décision de politique v1 (policy, avant chaque outil)

Entrée : `session_id`, `run_id`, `principal`, `interface`, outil, arguments (visibles par la politique, jamais
journalisés en clair s'ils sont sensibles), mode de bac à sable courant.
Sortie : `allow` | `ask(answerer, reason)` | `deny(reason)`, enregistrée dans le Run Plane et walter_logs.

Les sources sont ordonnées, et **le refus l'emporte** :
1. liste NEVER et profondeur de délégation ;
2. garde de divulgation (messages sortants, même règle que `disclosure_hook.py`) ;
3. périmètres Computer Use par interface (`modules/computer-policy.json`) ;
4. autorisations de comptes (`walter_secrets.grants`) ;
5. bac à sable et approbation du noyau.

Sans répondant disponible (Telegram hors ligne, mode commande), une demande échoue fermée.

### 4.5 Vocabulaire des événements

- **Journal d'exécution** : le vocabulaire walter_logs existant (`user/message`, `assistant/message`,
  `assistant/reasoning`, `tool/call`, `tool/result`, `compaction/summary`, `model/selection`…). Il vient déjà de DSH
  et ne change pas.
- **Bus** : `turn.started`, `turn.ended`, `session.ended`, `run.started` / `run.ended` (déjà émis par le Run Plane),
  `approval.requested` / `approval.answered`, `delegation.started` / `delegation.ended`, `engine.recovered`. Chaque
  événement porte `run_id`, `session_id` et `interface`.

### 4.6 Déclaration d'une stratégie

Une stratégie est un greffon Cordis avec un en-tête déclaratif : point d'extension, identifiant remplacé, contrats
lus et écrits, interrupteur, propriétaire, tests. Elle est déclarée dans le contrat de core (`contracts/core.json`,
liste des composants, § 8) et chaque composition la nomme explicitement. Une composition qui laisse un point
d'extension sans stratégie, ou qui en met deux, est refusée par `walter check`.

## 5. Les fonctions demandées, une par une

### 5.1 Sessions persistantes
- Identifiant stable par porte : `web/…`, `telegram/<chat>`, `api/<appelant>/<id>`, `command/<run>`. Le noyau ne
  reprend une session que si son identifiant est stable : c'est l'intake qui le fixe.
- Les **fils** de Walter (threads, possédés par Memory) traversent les sessions : le ThreadHint v1 relie chaque tour à
  son fil. Le moteur ne crée pas de notion de fil.
- Stockage : JSONL du noyau, compressé, avec points de reprise. C'est son stockage de travail, comme `state.db` pour
  Hermes. walter_logs en est la copie d'observabilité, alimentée par `walter-logs-watch` en quelques secondes. Il n'y
  a qu'un journal d'exécution au sens de Walter : walter_logs.

### 5.2 Appels d'outils
- Outils de base du noyau sous bac à sable. Outils Walter par le client MCP du noyau, vers `core/server.py`, avec le
  jeu d'outils de l'interface (`toolsets.toml`).
- Les outils à effet externe reçoivent l'identifiant d'appel (`exec.callId`) comme clé d'idempotence, transmise aux
  outils Walter qui écrivent (coffre, messages, mémoire).

### 5.3 Sous-agents
- Sous-agents en processus du noyau, réactivés. La stratégie Walter fixe le dossier de départ (ChildContextSpec),
  le plan (réutilisé ou demandé), le modèle (par le Router), les droits (§ 4.4), le budget et la profondeur maximale.
- `walter_run` devient un outil natif du moteur pour les sessions du moteur, sans aller-retour MCP, et une opération
  `delegate` de l'Engine API pour les appelants externes.
- Les médias (images, vidéo, musique) restent un pipeline du Router, qui n'est pas une boucle d'agent. Sa
  préparation d'invite cesse de passer par Hermes.

### 5.4 Interruptions
- Nouveau message pendant un tour : orientation ou mise en file (mécanisme du noyau), selon la porte.
- Arrêt : `turn.cancel` (bouton web, `/stop` Telegram, API). Les enfants s'arrêtent avec leur parent.
- Budget : le greffon budget arrête le tour par `agent/turn-stopping` quand le contrat d'effort est atteint, puis
  rend ce qui a été trouvé.

### 5.5 Permissions
- Un preset par porte et par principal : web propriétaire = espace de travail en écriture ; Telegram = lecture et
  outils Walter, actions sensibles soumises à approbation ; mode commande = restreint ; essais Lab = bac à sable
  isolé.
- Répondants d'approbation : l'interface web aujourd'hui, Telegram ensuite (boutons). La politique reste au même
  endroit (`core/security`), les répondants ne font que transmettre.

### 5.6 Événements
- Émis nativement par le greffon events, plus par un script shell à chaque message. Le bus et le Run Plane sont
  écrits par la passerelle Memory, qui reste la seule porte d'écriture. Deux routes y sont à ajouter : `/v1/runs/*` et
  `/v1/bus/emit`. Le bus garde son interface quand il passera physiquement dans `core/bus`.
- `SessionEnd`, absent du pont de hooks, est émis par le greffon events à la fermeture ou à l'expiration d'une
  session.

### 5.7 Reprise après incident
- Points de reprise du noyau : avant chaque appel de modèle, avant chaque outil à effet, avant l'étape suivante.
- Au redémarrage, les sessions se rouvrent à la demande. Un appel sans résultat est marqué « issue inconnue » et
  n'est jamais rejoué automatiquement. Le run passe `interrupted`, l'interface d'origine est prévenue
  (`engine.recovered`) et le propriétaire décide.
- `runs.sweep` ferme les runs abandonnés. systemd redémarre l'hôte (`Restart=on-failure`). Le guardian de core sonde
  l'Engine API et l'interface web.

## 6. Le flux d'une requête (vision § 8)

```
1 Entrée        porte → Engine API → intake : owner-turn, session stable, runs.start
2 Preflight     walter-context /preflight → ContextPlan v2 (intention, niveau, capacités, effort, voie sans modèle)
                ├─ voie sans modèle → réponse, fin du tour (0 modèle)
                ├─ Context + Memory : contexte selon le plan (mémoire seulement si le plan la demande)
                └─ Router : walter-llm lit le plan du run → modèle, fournisseur, effort ; abonnements d'abord
3 Runtime       boucle du noyau : étapes, outils (politique avant chacun), sous-agents, budget
4 Persistance   réponse → porte ; JSONL + points de reprise ; walter_logs ; bus turn.ended ; Run Plane ;
                Memory consolide (épisodes, vues) en réagissant aux événements
```

## 7. Branchement aux autres modules

| Module | Ce que le moteur en utilise | Interface | Sens |
|---|---|---|---|
| Context (cognition) | preflight, ContextPlan, pack, ChildContextSpec, compaction | HTTP :8897, prise DSH, schémas | moteur → context |
| Router (cognition) | choix du modèle, passerelle de modèles, coûts, abonnements | OpenAI-compatible :8894 (`model=auto`) | moteur → router |
| Memory (cognition) | Run Plane, bus, `core.events` (par ses connecteurs), vues | passerelle :8890 (+ routes runs et bus) | moteur → memory ; memory consomme walter_logs |
| Observabilité du Core | walter_logs (journal brut), santé | `walter-logs-watch`, schéma `walter_logs` | moteur → logs |
| Soul (core/identity) | instructions du moteur | rendu `AGENTS.md` | soul → moteur |
| Skills, Browse, Computer, Colab (capabilities) | capacités | MCP walter (jeu d'outils par interface) | moteur → capacités |
| Secrets (core/security) | autorisations de comptes, injection sans valeur visible | `walter-secret`, MCP sans valeur | moteur → secrets |
| Ops | installation, gel, déploiement, sauvegarde, restauration | `walter-ops`, `walter compose` | ops → moteur |
| Lab | compositions variantes, banc | `walter-scenario`, `walter matrix` | lab → moteur (proposer, jamais déployer) |

Ce que le moteur **ne** fait **jamais** : appeler un fournisseur de modèle sans passer par la passerelle, lire la
mémoire sans passer par Memory ou Context, garder sa propre mémoire, ses propres skills ou son propre registre,
lancer Hermes.

## 8. Documentation auto-descriptive (règle du 09/11)

On réutilise les mécanismes existants, sans seconde source :

- **Registre** : le contrat de chaque module (`contracts/<module>.json`, compilé dans `modules/registry.json`) reçoit
  une liste `components` : chemin, rôle, propriétaire, contrats, état, README. Le moteur y entre comme composant de
  core, ses greffons comme sous-composants.
- **Présentation aux agents** : les niveaux M0, M1, index et guide (`manifest/`) restent la porte des agents ; le
  moteur y ajoute sa section quand il entre en service.
- **README d'en-tête identique** dans chaque composant et dans chaque dossier annexe (bench, ops, ports, tests…) :
  Rôle, Propriétaire, État, Ne fait pas, Contrats, Pour un agent.
- **Contrôle** : `walter check` signale un composant déclaré sans README conforme, puis le refuse une fois le stock
  rattrapé. `docs/contracts.generated.md` reste la vue générée de l'ensemble.

## 9. Risques et points ouverts

| Sujet | Risque | Réponse prévue |
|---|---|---|
| Noyau en version préliminaire (rc.2) | Défauts amont, changements d'interface | Gel exact, mise à jour seulement par Lab, une composition de repli |
| Disque à 94 % (9,5 Go libres) | Le gel du noyau (524 Mo) et les essais de restauration manquent de place | Gel par déplacement plus lien (pas de copie), cache hors ligne dédoublonné ; nettoyage disque à prévoir avec Ops |
| Mémoire vive d'un hôte unique | Web, API et enfants dans un seul processus Node | Mesure au lot E4 ; plafond mémoire systemd ; enfants hors processus seulement si mesuré nécessaire |
| Fidélité de la reprise | Pas d'« exactement une fois » | Clés d'idempotence, issue inconnue, décision du propriétaire |
| Points d'extension manquants | Un besoin Walter sans point d'extension public | Consigné, étudié par Lab ; correctif amont proposé ou bifurcation documentée, jamais un correctif silencieux |
| Approbations ponctuelles seulement | Trop de demandes sur Telegram | Presets par porte ; règles mémorisées seulement après étude Lab et accord |
