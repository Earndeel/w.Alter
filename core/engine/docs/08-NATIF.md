# 08 — Walter Engine natif : bascule hors DSH (17/11/2026)

Mission de Monsieur du 17/11 (« Walter Native Engine × Cognitive Architecture ») : Walter Engine possède tout son
runtime. Il démarre, reçoit des messages, raisonne, exécute des outils, délègue, reprend ses tâches et fonctionne
**sans aucun processus, paquet ou composant runtime DSH/Cordis**. Ce document dit ce qui a été remplacé, ce qui a été
prouvé, avec DSH réellement arrêté, et ce qui ne l'est pas encore.

## 1. État en service (17/11, bascule à 16:21 UTC)

| Élément | Où | État |
|---|---|---|
| Moteur natif (boucle, sessions, outils, Python, sous-agents, tâches, réveils, reprise, Engine API v1, porte web) | `core/engine/walter_engine/` (≈ 5 400 lignes Python), unité `walter-engine.service` | **En service** : Engine API 127.0.0.1:8895, porte web 127.0.0.1:3080, état `@instance/state/core/engine/native` |
| DSH (`dsh-web`) | `/opt/dsh` (gelé, inchangé) | **Arrêté, désactivé, masqué** ; unité gardée dans la sauvegarde pour le retour arrière |
| Preuve « sans DSH » | drop-in `walter-engine.service.d/90-validation-sans-dsh.conf` (`InaccessiblePaths=/opt/dsh`) | Le moteur et tout ce qu'il lance (bash, Python, sous-agents) ne voient pas `/opt/dsh` : une dépendance cachée échouerait |
| Reprise des conversations DSH | `walter-python -m walter_engine import-dsh` | 199 conversations reprises, mêmes numéros `seq` (un client reprend où il en était), idempotent, fichiers DSH seulement lus |
| Portes | `walter-telegram`, `walter-web-gate` (drop-ins `20-walter-engine.conf`) | Inchangées : elles parlent l'Engine API et la porte web, servies par le natif |
| Garde-fou core, registre, scénarios | `guardian/check`, `contracts/core.json` → `modules/registry.json`, `scenarios/` | Suivent l'unité moteur activée (`walter-engine`, ou `dsh-web` après un retour arrière) |
| Identité | walter-soul, cible `engine` → `@instance/profiles/engine/AGENTS.md` | Identité + règles + « Outils enchaînés » (Python, `await tools.x()`, `asyncio.gather`) |
| Outils Walter (MCP) | `tools/mcp.py`, `core/config/toolsets.toml [clients.engine]` | Même jeu `core` que DSH (19 outils listés) ; les autres par `walter_call` |

Le moteur ne réimplémente aucun module : runs, bus et contrôle de divulgation chez Memory (passerelle :8890), plan et
fenêtre de contexte chez Context (préflight), modèles chez le Router (walter-llm :8894), politique dans
`core/security`. Le seul code DSH encore lu est l'importeur (une fois, à la migration) : `config.dsh_home` ne sert
qu'à `import-dsh`.

## 2. Matrice de parité (fonctions DSH réellement utilisées → natif)

Usage : appels d'outils des sessions DSH journalisés dans walter_logs (toute la vie de DSH). « Python » = joignable
depuis le noyau par `await tools.<nom>(…)`, sous la même politique et le même journal qu'un appel direct.

| Fonction DSH (usage) | Contrat dont Walter dépend | Natif | Python | Preuve (17/11, DSH arrêté) | Écart justifié |
|---|---|---|---|---|---|
| Boucle agentique : tours, pas, outils en parallèle sûrs | Engine API v1 (`turn.submit`, résultat, flux) | `engine.py` | — | toutes les vérifications ci-dessous | aucun |
| Sessions, continuité, journal | journal JSONL au vocabulaire DSH (`turn/start`, `tool/call`…) | `journal.py` (un fichier par session, verrou exclusif) | — | `engine_api_e2e` continuity/restart ; import 199 sessions | journal en clair (DSH : zstd) |
| `bash` (502), tâches de fond `job_output` (55), `job_kill` (3), `job_list` (1) | outils de base | `tools/builtin.py`, `jobs.py` | oui | `engine_native` bash_job ; réveil à la fin | aucun |
| `read` (61), `write` (46), `edit` (30), `grep` (12), `glob` (10), `read_image` (20), `present` (5) | outils de base | `tools/builtin.py` | oui | `engine_native` python_tools (read + glob en `gather`) | aucun |
| `ask_user_question` (0), `context_recover` (0) | outils de base | `tools/builtin.py` | oui | tests hors ligne | jamais utilisés en production |
| `subagent` (57), `send_message`, `interrupt_agent`, `list_agents` | délégation v1, profondeur ≤ 3, enfant ≤ parent | `tools/agents.py` | oui | `engine_native` subagent + background ; `engine_e5` | aucun |
| `python` (7) + appels d'outils depuis le noyau (`ptc-dispatch`, 4) | protocole walter-1 (`plugins/python/runtime`) | `tools/python.py` | — | `engine_native` python_persist, python_tools, restart (variables restaurées) | **droits du moteur** (`python = "full"`, Monsieur 17/11) au lieu de la bulle `walter-sandbox` ; la bulle reste un réglage (`python = "sandbox"`) |
| Outils Walter MCP (41-42), `walter_call` (67) | MCP `core/server.py`, jeu `core` | `tools/mcp.py` (client tag `engine`) | oui | `walter_v1_live` (mémoire, navigation, Router) | aucun |
| Accueil d'un tour (greffon intake) : run Memory, plan et paquet de contexte, texte du propriétaire | `turn-intake.v1`, ContextPlan v2, `/v1/runs/start|end` | `walter.py`, `engine.py` (`_intake`) | — | `v1_criterion` étapes 1–3 | aucun |
| Politique (greffon policy) : jamais-liste, préréglage par porte, enfant ≤ parent, divulgation, accords | `core/security/policy.json` | `policy.py` | même politique | `engine_api_e2e` never + approval ; `engine_e5` policy | aucun |
| Plafonds du tour (greffon budget) | `[dsh.budget]` par niveau d'effort | `engine.py` (lit le même bloc) | — | test hors ligne | aucun |
| Fin de tour (greffon events) : run fermé, `turn.ended` | bus `turn.ended`, `/v1/runs/end` | `engine.py` | — | bus : 59 `turn.ended` source `walter` | `session.ended` non émis : DSH n'en a jamais émis (0 sur le bus) |
| Réveil : tâche ou sous-agent fini → avis ; pendant un tour → inséré dans ce tour | `agent/inbox/spliced` (2 292 chez DSH) | `engine.py` | — | `engine_native` background, bash_job (les deux formes) | aucun |
| Reprise après redémarrage et crash | point durable avant appel ; « résultat inconnu » jamais rejoué | journal + `resume_interrupted` | variables du noyau restaurées | `engine_native` restart + crash (effet de bord exécuté une seule fois) ; `engine_api_e2e` restart | aucun |
| Compaction | DSH : compresseur natif | fenêtre décidée par walter-context (`compaction/window`), originaux gardés | — | 21 fenêtres dans les journaux natifs | amélioration : Context décide, rien n'est perdu |
| Titres de conversation | `session/title` | `engine.py` (`_title`) | — | titres dans les journaux natifs | aucun |
| Engine API v1 (ouverture, envoi idempotent, accords, annulation, flux SSE, délégation) | `engine/contracts/engine-api.v1.json` | `api.py`, `server.py` | — | `engine_api_e2e` 7/7 | aucun |
| Porte web (3080) : connexion par cookie, hôtes de confiance, panneaux, liens | cookies DSH acceptés | `server.py`, `ui/` | — | tests hors ligne ; portail 401 sans cookie, 403 hôte inconnu | pièces jointes et « changements de l'espace de travail » de l'interface DSH non repris (0 et 5 usages) |
| `/stop`, annulation | `turn.cancel` | `api.py` | — | `engine_api_e2e` cancel ; `telegram_door` stop | aucun |
| Délégation `walter_run` / `walter-router run` | `delegate` v1 | `api.py` | — | `engine_e5` delegate, router | run d'un compte de test au canal `test` (§10), plus `machine` |
| walter_logs (observabilité) | journal de session lu par `walter-logs-watch` | dossier natif surveillé | — | 4 688 lignes relues, 209 insérées au redémarrage du veilleur | aucun |
| core.events (conversations du propriétaire) | `agent-sessions --walter` | `connectors/agent_sessions.py` | — | tests unitaires ; **pas encore de conversation réelle de Monsieur depuis la bascule** | compte de test, délégations et sous-agents restent dans walter_logs |

Aucune capacité de DSH n'a disparu sans être nommée ici. Les écarts sont : Python avec les droits du moteur (décision
de Monsieur), la compaction confiée à Context, le canal `test` des délégations du compte de test, et deux fonctions
d'interface web jamais ou presque jamais utilisées (pièces jointes, changements de l'espace de travail).

## 3. Validation avec DSH arrêté (production, compte de test `e2e`, contenus synthétiques)

| Scénario | Résultat | Notes |
|---|---|---|
| `scenarios/v1/engine_native.py` (Python persistant, outils depuis Python, sous-agent, sous-agent de fond, tâche bash de fond, redémarrage, crash) | **7/7** | crash : appel sans résultat → « résultat inconnu », tour `interrupted`, effet de bord exécuté une seule fois |
| `scenarios/v1/engine_api_e2e.py` (ouverture, envoi + rejeu, continuité, jamais-liste, accord refusé, annulation, redémarrage) | **7/7** | |
| `scenarios/v1/engine_e5.py` (profondeur, délégation + rejeu, `walter-router run`, deux sous-agents en parallèle, politique d'un enfant, interruption) | **6/6** | le sous-agent se voit refuser `cat /root/.pgpass` (jamais-liste) |
| `scenarios/v1/engine_e8.py` (modèle refusé, échec d'outil, porte redémarrée, **moteur redémarré en plein tour**, budget, rejeu de délégation) | **6/6** (4 au 1er passage, les 2 autres après correction du scénario) | redémarrage : la porte dit « je reprends », le message du propriétaire n'est pas rejoué (1 fois au journal), la demande coupée est reprise par le moteur, la conversation retient le code donné avant |
| `scenarios/v1/telegram_door.py` (identité, continuité, rejeu d'un message, accord refusé par bouton, `/stop`) | **5/5** (4 au 1er passage : `/stop` tombait sur une demande d'accord du compte de test) | la porte affiche « en train d’écrire », un message rejoué n'est répondu qu'une fois, `/stop` → « ⏹ Interrompu. » |
| `scenarios/v1/walter_v1_live.py` (mémoire, navigation, Router, trace) | **4/4** (3 au 1er passage : défaut du Router, corrigé) | 9 appels de modèle, tous comptés au journal de la passerelle, 0 $ (routes d'abonnement) ; événements du bus du run, de la tâche et de l'épisode présents |

Corrections de scénario, pas du moteur : un avis de fin qui arrive pendant le tour est inséré dans ce tour (comme
DSH), le test attendait un nouveau tour ; le compte de test est jugé sous le préréglage `test` (chaque appel sensible
demande un accord) : les scénarios répondent désormais à leurs propres demandes (`telegram_door.auto_allow` par les
boutons de la porte, `approval.answer` pour E5) ; une session native a la clé `walter/vm/<id>` dans walter_logs (les
conversations importées gardent `dsh/vm/<id>`) ; le bloc de contexte que walter-context ajoute au tour cite le message
de l'appelant et n'est pas un rejeu (E8 ne compte que les messages de source `user`).

Cinq corrections du système trouvées par ces passages et la vérification qui a suivi :
- **Porte Telegram** : après un redémarrage elle disait « Redis-moi si je dois reprendre » alors que le moteur natif
  reprend seul la demande ; elle demande désormais au moteur s'il reprend (santé `resumes_interrupted`) et dit « je
  reprends là où j'en étais » (DSH : message d'avant).
- **Router** : un agent a demandé `walter_route` avec la tâche « image » (le nom est `text_to_image`) ; l'appel
  mourait (`KeyError`, rendu « RuntimeError » sans détail par le serveur MCP). Un nom de tâche inconnu est maintenant
  ignoré et dit (`task_ignored`), la demande décide.
- **Tour de test resté en attente** : un tour de test repris après redémarrage attendait un accord que personne ne
  donnait ; il ne bloque pas la conversation (le message suivant est mis en file et répondu après), mais la session
  reste active. Les scénarios répondent désormais à leurs accords ; un tour de test abandonné se ferme par
  `turn.cancel`.
- **Memory, lecture « cloud-safe »** : la clé Liquid, collée en clair dans le message de mission, ressortait d'une
  recherche mémoire parce que la détection de secrets ne reconnaissait pas les valeurs du coffre. `privacy.detect`
  reconnaît désormais toute valeur présente dans Bitwarden (empreintes de Walter Secrets) ; la lecture la masque.
- **Santé de Memory** : les appels doublés volontairement (`hedged`, `straggler`, `unsupported`) étaient comptés
  comme refus de budget et faisaient tomber le score de l'autopilote à 75 ; ils sont notés `dropped` (ni réussis ni
  échoués), 1 266 lignes passées reclassées (liste des identifiants gardée pour le retour arrière) ; score 100.

Vérification finale (tests du module core, 17/11 ≈ 17:10), quatre écarts de la bascule corrigés :
- le guide du gardien core ne nommait que `dsh-web` : il n'aurait pas pu relancer un `walter-engine` arrêté ou
  périmé ; il nomme désormais `walter-engine` (et `dsh-web` pour le retour arrière) ;
- `walter deploy` ne différait pas un redémarrage de `walter-engine` pendant un tour (il ne comptait que les runs
  `dsh`) : il compte aussi les runs natifs (`walter`) ;
- `walter_health` (MCP) lisait l'état de `dsh-web` : il lit l'unité moteur activée ;
- le moteur nommait en dur les dossiers de Memory et de Context (règle d'interconnexion) : il passe par le client
  public de Memory et par `walter path`. Moteur relancé à 17:15 UTC (aucun tour en cours), `check` vert.

## 4. Chemin critique (mission § 9)

**Que fait Walter entre l'arrivée d'un message et la première action utile du modèle principal ?** Mesures du
17/11 sur les tours natifs (n = 22 à 31, tours de test) :

| Étape | p50 | p90 | p99 / max |
|---|---|---|---|
| Accueil : run Memory + préflight (plan + contexte) + fenêtre | 1,59 s | 2,38 s | 3,27 s |
| Premier mot du modèle principal (TTFT, 1er pas) | 4,04 s | 7,25 s | 9,49 s |
| Début du tour → premier mot | 5,17 s | 10,2 s | 11,3 s |
| Début du tour → premier appel d'outil | 6,87 s | 10,8 s | 11,5 s |

Le préflight (production 16–17/11, 92 tours) : décision p50 734 / p90 1 190 / p99 2 120 ms ; récupération p50 503 /
p99 3 418 ms ; total p50 1,27–2,16 s, p99 4,7–5,5 s. **Le premier mot du modèle principal coûte 2,5 fois le
préflight** (routes d'abonnement, ≈ 10 600 jetons d'entrée pour un tour simple) : c'est lui, pas la décision, qui
domine l'attente.

Banc du chemin critique (Context `bench/critical_path.py`, 21 cas synthétiques, décisions fraîches) :

| Mode | Qualité de la décision | Total p50 / p90 / max (ms) | Jetons du paquet p50 |
|---|---|---|---|
| ancien préflight | 0,556 | 656 / 942 / 3 737 | 1 584 |
| préflight + état vivant | 0,524 | 660 / 930 / 1 031 | 2 199 |
| direct (sans décision probabiliste) | 0,270 | 447 / 513 / 570 | — |
| adaptatif (décision plafonnée à 400 / 600 / 800 ms, sinon direct) | 0,45 / 0,508 / 0,508 | — | — |

Conclusions appliquées :
- L'état vivant ne donne **aucun gain** de décision mesuré (0,524 contre 0,556, même latence, plus de jetons) : les
  interrupteurs `[state]` du préflight restent à `false`. Le WorkingState sert le moteur (événements d'état,
  réévaluation § 7), pas le préflight.
- L'exécution directe divise la qualité par deux pour 200 ms : refusée. L'adaptatif perd en qualité dès qu'il coupe.
- Une attente séquentielle injustifiée supprimée : le cache des notes de modules (`walter present`, ≈ 1,2 s à froid)
  est servi périmé et rafraîchi à côté ; bloc `tool_cards` max 1 194 ms avant, 0 ms après (6 tours).
- Appels inutiles : 24/63 récupérations sans besoin, identiques ancien / vivant ; l'erreur principale est de demander
  Memory quand l'état contient déjà la réponse.

Anomalies, sans moyenne qui les cache :
- p99 de la passerelle : Drex (Nace) p50 0,52 / p90 0,94 / p99 3,42 s (n 2 737) ; la latence monte à partir de 6
  appels simultanés (p90 2,6–3,9 s).
- 429 de Nace : 191, **tous pendant des rafales de bancs**, aucun en production.
- d1.2-ultra : p50 0,68 / p90 3,04 / p99 7,02 s, 9 délais dépassés (n 733) ; banc Liquid direct : 0,34–0,36 s p50,
  d1.2 réveil à froid ≈ 9,5 s après ≈ 7 min d'inactivité (natif comme OpenRouter).
- Lectures tardives du préflight : 0 ; rattachements de run tardifs : 0.
- Lancement d'un noyau Python : 61–84 ms en mode `full` (restauration comprise), 110–125 ms en bulle.
- Goulots de DSH : aucun mesurable sur l'accueil (1,31 s p50 avant la bascule, 1,43 s après, même préflight) ; la
  différence est dans le bruit.

Non mesuré : la qualité d'exécution du modèle principal par mode (le banc juge la décision, pas l'exécution).

## 5. Sécurité

- Le moteur est root et administre l'hôte par `bash` sous la politique unique ; le noyau Python a les mêmes droits
  (décision de Monsieur du 17/11). Ce qui borne un appel : la jamais-liste (déterministe, avant exécution, aussi sur
  le texte d'une cellule Python), le préréglage de la porte, l'enfant ≤ parent, le contrôle de divulgation de Memory,
  les plafonds du tour. Aucune sécurité ne repose sur le jugement d'un modèle.
- Les commandes ne voient jamais les jetons du moteur (test hors ligne `test_commands_never_see_the_engine_credentials`).
- La clé Liquid est dans Bitwarden et sa carte de droit ; aucun fichier, journal d'agent, banc, sauvegarde ou commit
  ne la contient. Elle reste dans l'historique de Memory (le message de mission où elle a été collée, et son index de
  recherche) : l'historique est append-only, la lecture la masque désormais ; **la faire tourner** reste conseillé.
- Sans accord interactif systématique : le propriétaire n'a pas de demande ; le compte de test, lui, en a à chaque
  appel sensible (le chemin d'accord est exercé à chaque scénario).

## 6. Retour arrière

`/user/Lucas/backups/changes/2026-11-17-native-engine/README.md` § 1 : moins d'une minute, sans perte (l'état DSH n'a
pas été modifié ; les conversations tenues pendant la période native restent dans l'état natif). Le garde-fou core,
`walter_health`, le report des redémarrages pendant un tour et les scénarios suivent seuls l'unité activée ; le contrat
`core` déclare `walter-engine` : un retour arrière durable y remet `dsh-web` (et dans le guide du gardien).

## 7. Ce qui reste (non fait, ou fait mais pas prouvé)

1. Ingestion en mémoire d'une **vraie** conversation de Monsieur par le moteur natif : testée hors ligne, pas encore
   observée (aucune depuis la bascule).
2. Pièces jointes et « changements de l'espace de travail » dans la porte web native (non repris, 0 et 5 usages).
3. Un redémarrage du moteur coupe les requêtes longues en attente (`turn.submit` avec `wait_ms`) avec une trace
   d'erreur d'uvicorn ; le tour lui-même est fermé `interrupted` et repris, le client doit relire son résultat.
4. Le drop-in `InaccessiblePaths=/opt/dsh` est gardé tant que DSH reste installé (preuve permanente) ; la
   désinstallation de DSH n'est pas faite.
5. TTFT du modèle principal (≈ 4 s p50) : hors du préflight, piste suivante (cache de préfixe, jetons d'entrée).
6. `scenarios/v1/v1_criterion.py` (critère V1 de bout en bout) et `scenarios/socle/socle_e2e.py` : adaptés au
   moteur natif (unité, clés de session, compte de test sans écriture dans Memory), **pas encore rejoués** sous le
   moteur natif.
