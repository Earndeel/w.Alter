# Plan de migration incrémentale du runtime unique

| | |
|---|---|
| **Rôle** | Ordonner le passage des boucles actuelles (DSH tel quel, `walter_run`, rôles de Hermes) au moteur unique `core/engine`, lot par lot, avec tests, critères d'adoption et retour arrière. |
| **Propriétaire** | walter-core (exécution : le builder ; validation : Monsieur). |
| **Statut** | 09/11/2026 · **à valider par Monsieur. Aucun lot n'est lancé avant son accord.** |
| **Sources** | `01-AUDIT.md`, `02-ARCHITECTURE.md`, `VISION.md` § 9 (« évolution mesurée »), plan du 08/11 (lots A–D de `walter_run`). |

## Règles communes à tous les lots

1. **Un lot = un changement réversible.** Avant chaque lot : étiquette git `engine-E<n>-avant` dans les dépôts
   touchés, sauvegarde des fichiers d'état dans `/user/Lucas/backups/changes/<date>-engine-E<n>/`.
2. **Ombre d'abord quand c'est possible** : le nouveau chemin calcule à côté de l'ancien et on compare, puis on
   bascule par un interrupteur dans la configuration de la composition, pas par une réécriture.
3. **Aucun module déplacé avant E9.** Les nouveaux fichiers naissent à leur place cible (`core/engine/…`), les
   anciens restent en place jusqu'à leur mise en quarantaine.
4. **Tests minimaux de chaque lot** (en plus des tests propres au lot) :
   - tests de core, de context et du router (`pytest`) et tests des greffons ;
   - `walter check` (contrats, frontières, neutralité) ;
   - `walter-scenario` de bout en bout sur la composition web ;
   - banc de contexte (`levels.py`, plancher actuel 17/18 en rappel) ;
   - santé : `walter status`, `walter-memory health`, `memory-autopilot` si Memory est touchée.
5. **Budget** : bancs sur fournisseurs payants plafonnés à 2 €/24 h ; au-delà, accord de Monsieur.
6. **Retour arrière** documenté et essayé une fois avant l'adoption, pas seulement écrit.
7. Chaque lot met à jour les README des composants touchés, le contrat de core et `DECISIONS.md`.

## Vue d'ensemble

| Lot | Objet | Change la production ? | Dépend de |
|---|---|---|---|
| **E0** | Contrats en schémas, registre des composants, mesures de référence | Non | — |
| **E1** | Geler le noyau DSH dans `core/engine/kernel` | Oui (même code, autre emplacement) | E0 |
| **E2** | Accueil et événements natifs (fin du script shell par message) | Oui, après ombre | E1 |
| **E3** | Politique : divulgation, approbations, budget de tour | Oui | E2 |
| **E4** | Engine API v1 | Ajout seulement | E2 |
| **E5** | `walter_run` → sous-agents du moteur | Oui, avec repli | E3, E4 |
| **E6** | Fin des rôles de production de Hermes (hors Telegram) | Oui | E4 |
| **E7** | Interface Telegram sur le moteur | Oui, après une semaine en parallèle | E3, E4 |
| **E8** | Reprise après incident éprouvée ; étude Lab du stockage Postgres | Non (essais) puis peut-être | E2 |
| **E9** | Migration des dossiers selon la vision | Oui (liens de compatibilité) | E7 |

E4 et E8 peuvent avancer en parallèle de E3. E6 peut commencer dès E4.

## E0 — Contrats, registre, référence

- **Fait** : schémas JSON (`core/engine/contracts/`) pour Engine API v1, accueil, Délégation v1, Décision de
  politique v1, vocabulaire des événements, déclaration d'une stratégie. Liste `components` dans
  `contracts/core.json`, compilée dans le registre. En-tête README standard et son contrôle par `walter check` (en
  avertissement). Mesures de référence de la production actuelle : latence du premier jeton, coût par tour, rappel
  `levels.py`, mémoire vive de `dsh-web`, délai walter_logs.
- **Tests** : validation des schémas sur des exemples réels tirés de walter_logs et du Run Plane (agrégats, pas de
  contenu personnel) ; `walter check` vert.
- **Adoption** : registre régénéré, `walter present` montre le moteur comme composant de core.
- **Retour arrière** : revert du commit (documentation et schémas seulement).

## E1 — Geler le noyau

- **Fait** : versions exactes de DSH et de ses dépendances (`package-lock`, empreintes d'intégrité), cache hors
  ligne, installation dans `core/engine/kernel` **par déplacement et lien** depuis `/opt/dsh` (disque à 94 %). Les
  compositions web et headless sont générées depuis `core/engine/compositions/` par walter-core. `dsh-web.service`
  devient `walter-engine.service` (même port :3080, même `DSH_HOME`, même stockage de sessions).
- **Tests** : installation propre depuis le cache hors ligne dans un dossier d'essai ; `--dump-config` identique
  avant et après, à l'ordre près ; scénario web, session existante reprise ; `levels.py`.
- **Adoption** : 48 h de service sans régression ; une réinstallation depuis le cache réussie.
- **Retour arrière** : surcharge systemd `ExecStart` qui repointe vers `/opt/dsh` (conservé jusqu'à E9), redémarrage.
  Moins d'une minute.

## E2 — Accueil et événements natifs

- **Fait** : greffon intake (owner-turn + appel direct au preflight + `runs.start` par la passerelle) ; greffon
  events (bus, Run Plane, `SessionEnd`). Ajout à la passerelle Memory de `/v1/runs/*` et `/v1/bus/emit`, la seule
  porte d'écriture. Identifiant de session stable par porte. Le hook shell `walter_hook.py` reste pour Claude Code et
  Codex, et n'est plus appelé par le moteur.
- **Ombre** : une semaine où les deux chemins tournent. Le greffon écrit avec un marqueur `shadow`, on compare plans,
  runs et événements, puis on bascule par l'interrupteur de la composition.
- **Tests** : même ContextPlan pour un même message (écart toléré : 0 sur l'intention et le niveau) ; un run par tour,
  jamais deux ; `session.ended` reçu ; voie sans modèle servie sans appel de modèle ; gain de latence mesuré (fin
  d'un processus Python par message).
- **Adoption** : zéro écart d'intention sur la semaine, latence égale ou meilleure.
- **Retour arrière** : interrupteur `intake=hook` dans la composition, redémarrage.

## E3 — Politique, approbations, budget

- **Fait** : greffon policy (ordre § 4.4 de l'architecture, refus prioritaire, échec fermé sans répondant), presets
  par porte, garde de divulgation dans le moteur, greffon budget alimenté par le contrat d'effort du ContextPlan.
  Le test-home cesse de partager les profils et sessions de production.
- **Tests** : jeu d'essais de politique (message sortant vers un tiers bloqué sans accord, Computer hors périmètre
  refusé, secret jamais rendu, approbation absente ⇒ refus) ; tour coupé au budget avec réponse partielle propre ;
  scénarios web inchangés pour les usages ordinaires.
- **Adoption** : tous les cas de politique passent ; aucune demande d'approbation de trop sur une semaine d'usage web.
- **Retour arrière** : retrait du greffon de la composition (le bac à sable et l'approbation du noyau restent).

## E4 — Engine API v1

- **Fait** : greffon hôte qui sert l'Engine API en local (jeton d'agent 0600, flux SSE, port libre choisi et déclaré
  dans le registre). Mode commande. Les essais Lab passent par elle.
- **Tests** : tests de contrat de chaque opération ; ouverture, reprise, annulation, file, approbation ; 20 sessions
  simultanées sans fuite de mémoire (plafond systemd) ; refus sans jeton.
- **Adoption** : contrats verts, mémoire vive stable sur 72 h.
- **Retour arrière** : retrait du greffon hôte ; rien n'en dépend encore.

## E5 — `walter_run` devient une délégation du moteur

Ce lot reprend et remplace les lots A–D du plan du 08/11.

- **Fait** : sous-agents du noyau réactivés sous la stratégie Walter (ChildContextSpec servi par le service context,
  plan réutilisé ou demandé une fois, droits ≤ parent moins NEVER, profondeur et budget). Outil natif `walter_run`
  dans le moteur ; l'outil MCP `walter_run` appelle l'opération `delegate`. La boucle `text_agent.py` reste derrière
  un interrupteur de repli pendant environ deux semaines, puis part en quarantaine avec `walter-tools serve`. La
  préparation d'invite des médias cesse d'appeler Hermes.
- **Tests** : scénarios `walter_run` existants rejoués (sorties validées par leur contrat) ; aucun `shell=True` hors
  bac à sable ; enfants annulés avec leur parent ; coûts et `task_id` présents dans le Run Plane ; observations
  toujours persistées dans Memory.
- **Adoption** : parité de réussite sur les scénarios et une semaine d'usage réel, coût par mission égal ou moindre.
- **Retour arrière** : interrupteur `walter_run.engine=false` ⇒ ancienne boucle (tant qu'elle n'est pas en
  quarantaine) ; ensuite, restauration depuis la quarantaine.

## E6 — Fin des rôles de production de Hermes (hors Telegram)

- **Fait** : `oneshot.ask_l1`, `media_exec` et les alertes du Router passent par le mode commande de l'Engine API ;
  les changements de configuration de Hermes disparaissent avec eux. L'autorisation Google passe par Secrets (grant)
  pour le moteur. La tâche nocturne Memory Dreaming, morte et payante, est supprimée (elle peut l'être dès maintenant
  si Monsieur le veut). La vérification de santé de Hermes passe aux guardians.
- **Tests** : tests du Router verts ; une proposition Telegram du Router produite sans Hermes ; aucun appel
  `hermes …` restant hors Lab (recherche dans le code).
- **Adoption** : un cycle de 48 h du Router sans Hermes.
- **Retour arrière** : par fonction, interrupteur qui revient à l'appel Hermes (Hermes reste installé jusqu'à E7).

## E7 — Telegram sur le moteur

- **Fait** : `core/interfaces/telegram` parle l'Engine API (session `telegram/<chat>`, `/stop`, boutons
  d'approbation, pièces jointes, voix via le STT du Router). Une semaine en parallèle sur un second bot ou une
  conversation d'essai, puis bascule du bot principal. Hermes devient objet d'étude de Lab, sa passerelle est
  arrêtée et non supprimée.
- **Tests** : liste de parité (les usages réels de Telegram relevés par agrégats dans walter_logs) ; reprise de la
  conversation après redémarrage ; approbation par bouton ; mémoire de la conversation retrouvée par Memory.
- **Adoption** : liste de parité complète et accord explicite de Monsieur pour la bascule.
- **Retour arrière** : `hermes gateway start` sur le bot principal (le jeton n'a pas changé), arrêt de l'interface.

## E8 — Reprise après incident

- **Fait** : essais de panne (arrêt brutal pendant un appel de modèle, pendant un outil à effet, pendant un enfant ;
  coupure de la passerelle Memory ; disque plein simulé) ; « issue inconnue » et `engine.recovered` vérifiés. En Lab
  seulement : étude d'un stockage de sessions dans Postgres au vocabulaire walter_logs (une seule source au lieu de
  JSONL + copie), adoptée seulement si mesurée meilleure.
- **Tests** : chaque scénario de panne finit avec un run fermé, aucun outil rejoué en double, la session reprise.
- **Adoption** : tous les scénarios passent deux fois de suite.
- **Retour arrière** : sans objet pour les essais ; pour un éventuel stockage Postgres, retour au JSONL par la
  composition.

## E9 — Dossiers selon la vision

- **Fait** : déplacements un module à la fois vers `core/`, `cognition/`, `capabilities/`, `ops/`, `lab/`, chacun
  avec son lien de compatibilité, mis à jour par `walter layout`. Retrait de `/opt/dsh` quand plus rien n'y pointe.
  L'instance reste `/user/Lucas` (système d'instances générique, aucune migration physique).
- **Tests** : `walter check` et tous les tests après chaque déplacement ; services redémarrés verts.
- **Adoption** : par module.
- **Retour arrière** : par module, le lien de compatibilité inversé.

## Ce que Monsieur valide maintenant

1. Le principe : **noyau DSH/Cordis figé + greffons Walter**, pas de réécriture, pas de troisième boucle.
2. L'ordre E0 → E9 et les critères d'adoption.
3. Deux points qui touchent d'autres modules : les routes `/v1/runs/*` et `/v1/bus/emit` ajoutées à la passerelle
   Memory (E2), et l'absorption des lots A–D du 08/11 par E5.
4. Facultatif : supprimer dès maintenant la tâche nocturne Memory Dreaming de Hermes.
