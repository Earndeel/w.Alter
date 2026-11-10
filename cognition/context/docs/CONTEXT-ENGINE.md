# walter-context — spécification et plan

Statut (2026-10-25) : **architecture v2 validée par le propriétaire** (moteur de contexte agentique, voir §0). Lots 0-2
faits ; **étapes A (contrats v1), B (preflight en fantôme) et C (vues v0 : les sujets) faites le 25/10, D (retrieval + assemblage en fantôme) le 26/10**. Analyse et plan d'intégration :
`~/reports/2026-10-25-walter-context-v2-integration.md`.

La version du 2026-10-11 (moteur de payload seul, mesures C0) est conservée dans
`~/.hermes/backups/retire-walter-compress-20261021/CONTEXT-ENGINE-20261011.md`.

## 0. Architecture v2 (le propriétaire, 25/10) — elle prime sur les §1 à §8 quand ils diffèrent
**Principe.**
- walter-memory organise ce que Walter sait.
- walter-context décide ce que le modèle doit savoir et pouvoir faire à cet instant.
- walter-router choisit l'intelligence.
- Le LLM reste libre d'approfondir et d'agir.

**Composants de walter-context.**
- **Preflight** → ContextPlan.
- **Retrieval** : vues, recherche hybride, logs, sources vivantes ; multi-étapes si nécessaire.
- **Compression** : état de travail minimal, adaptatif, jamais agressif par principe.
- **Assembly** : par modèle, blocs stables puis dynamiques, cache du fournisseur.
- Deux fonctions transversales : **Session State** et **Cache Policy**.
- La reconnaissance du sujet est une partie du preflight.

**Memory Views (lot 3, walter-memory).** Organisées par :
- domaine : projets, profil, activités, relations, agenda, décisions, objectifs ;
- temporalité : instant, jour, moyen terme, long terme, stable ;
- profondeur : index, aperçu, synthèse, détails, sources.

Elles sont versionnées, sourcées et datées pour la fraîcheur. walter-context demande la profondeur exacte.

**Capacités.**
- Chaque module expose M0 (une ligne, `manifest/SUMMARY.md`), M1 (`manifest/MANIFEST.md`) et M2
  (`manifest/GUIDE.md`) ; c'est le travail de la session « manifest », non committé au 25/10.
- M0 de tous les modules est toujours présent ; M1 seulement pour les modules utiles selon le plan.
- L'orchestrateur peut tout découvrir et approfondir. Les secrets restent des références.

**Contrats v1** (`walter_context/plan.py`, schémas générés dans `contracts/schemas/`) :
| Contrat | Contenu |
|---|---|
| **ContextPlan** | `turn_id`, `thread {id\|new, confidence, alternates}`, `act`, `level` L0-L4, `domains`, `horizons`, `capabilities` (tools, skills, search, delegation, secrets), `model_profile {task, level L1-L3, require}` (le Router choisit le modèle concret), `fast_path`, `escalated`, `decision` (trace) |
| **SessionState** | `thread_id`, `objective` (intention initiale), `constraints`, `decisions`, `refs`, `open_capabilities`, `plan` |
| **ThreadHint** | walter-context → Memory par le bus ; Memory décide du rattachement |
| **MemoryViewQuery** | `depth` + `key` ou `domain`, `horizon`, `max_tokens`, `max_age_s`, `privacy` ; la réponse appartient à Memory |

Niveaux de contexte :
| Niveau | Ce que voit le modèle |
|---|---|
| L0 | rien (les outils suffisent) |
| L1 | le dernier échange |
| L2 | le sujet en aperçu |
| L3 | le sujet en synthèse + mémoire ciblée |
| L4 | extensif, multi-étapes |

Les 4 plans du lot 1 correspondent à L0-L3.

**Étape D, retrieval et assemblage en fantôme (26/10).**
- **Preflight sur les vrais sujets.** Il demande ses sujets candidats à Walter Memory (`views.subject_candidates` :
  5 plus proches par embeddings locaux, plus le sujet en cours de la session). À chaud, il prend 0,66-0,69 s au
  total ; la latence de 0,6-0,7 s obtenue par la session « Vitesse du preflight » est conservée.
- **Retrieval** (`walter_context/retrieval.py`), selon le niveau :
  - L0 : capacités seules ;
  - L1 : index du sujet ;
  - L2 : aperçu du sujet ;
  - L3-L4 : synthèse du sujet (aperçu tant que l'étape E manque) plus la mémoire ciblée de Walter Memory (cloud-safe,
    rerank) ;
  - à tous les niveaux à partir de L1 : le tableau des sujets actifs et les 3 derniers échanges. Ces échanges sont
    comptés mais pas injectés quand l'hôte a son propre historique.
  - Capacités : M0 de tous les modules, M1 seulement des modules utiles au plan, via `walter present`.
- **Assembly** (`assembly.py`) : du plus stable au plus changeant, avec les tokens comptés par couche.
- **Fantôme.** Le hook envoie, après son injection actuelle, une demande détachée au service. Celui-ci note plan,
  paquet et injection actuelle dans `@instance/state/context/shadow/` (privé).
- **Rapport** : `walter-context-preflight --report [--days N]`.
- **Premier essai réel** (« ce qu'on avait décidé pour la vidéo Grok contre HeyGen ») : sujet juste (0,99), L2,
  paquet de 995 tokens par message contre 543 pour l'injection actuelle. Le plus gros bloc est le tableau des
  sujets (349 tokens), à revoir selon les mesures.

**Étape C, Memory Views v0 (25/10).** Les sujets dans Walter Memory : schéma `views`, rattachement continu de
chaque échange, fiche aux profondeurs index et aperçu, lecture par le contrat MemoryViewQuery (RUNBOOK § Memory
Views). Les profondeurs synthèse et détails, ainsi que les autres domaines (décisions, profil, relations, agenda,
activités), viennent à l'étape E.
Rattrapage du 25/10 : 288 échanges (après retrait de 16 doublons) en 33 sujets. Limite constatée : des sujets
trop larges (« Walter autonome en conteneur », 40 échanges sur 6 jours), dont la fiche ne garde que l'état
récent. L'étape E devra ajouter la synthèse, les cumuls journaliers et la scission des sujets trop larges.

**Étape B, preflight (25/10).** `walter_context/preflight`.
- **Un appel au modèle de décision du Router** (d1-ultra) répond à 11 questions : fil, acte, niveau, domaine,
  temporalité, niveau de modèle, famille de tâche, et 4 capacités en oui/non.
- **Règles sans appel** : réponse courte récente, calcul ou heure.
- **Plancher** : au moins le dernier échange si le message suit de moins de 30 min.
- **Stabilité et cohérence (09/11)** :
  - la décision = moyenne de 3 appels parallèles au même modèle (`llm.decide(samples=3)`) ; l'API échantillonne,
    mêmes entrées → capacité mémoire entre 0,37 et 0,55 sur un même message ;
  - capacité mémoire ⇒ niveau ≥ L3 : sur 203 tirages des 29 messages du banc, 77 (13 messages) disaient à la fois
    « mémoire nécessaire » et « rien au-delà du message / le fil suffit » ;
  - banc `bench/levels.py` (qui envoie désormais l'échange précédent au format du hook, `message/answer`), 2 passes
    avant / 3 après : niveaux justes 19–20/29 → 27–29/29, capacités 11/12 → 11–12/12, rappel 16/18 inchangé,
    0 fuite mémoire, cas instables entre passes 6 → 4 ; coût : +15 % de tokens injectés sur le banc (les questions
    mémoire reçoivent L3 au lieu de L0 + registre), latence médiane +230 ms (1,18 → 1,41 s), +0,00014 USD par
    message. Reste à la frontière : une question générique sur le système (mémoire ≈ 0,5) ;
  - preuves : `@instance/backups/changes/2026-11-09-context-preflight/` (`before/`, `after/`, `compare.py`).
- **Niveau incertain** (< 0,7) : tranché par le poste `general` du Router.
- **Confidentialité et pannes** : `local_only` ne sort pas ; en cas de panne, plan par défaut L1.
- **Point d'entrée** : `walter-context-preflight` (JSON en entrée, plan en sortie).
- **Fantôme** : le hook Claude Code le lance détaché à chaque message de le propriétaire, le plan est noté dans
  `@instance/state/context/shadow/preflight-<jour>.jsonl` (privé), rien n'est injecté, le hook rend la main en
  22 ms. DSH est exclu (son bac à sable tue les processus détachés) ; Codex n'a pas de hook avant le message.
- **Latence mesurée** :
  - décision à 11 questions ≈ 2 s (contre 0,6 s à 5 questions) ;
  - escalade ≈ +4 s ;
  - à réduire avant toute injection réelle : questions conditionnelles, escalade asynchrone.

## 1. La cible
À chaque appel de modèle, walter-context décide de ce qui entre dans la fenêtre : **quoi, combien, où, sous quelle
forme**. Trois propriétés, demandées par le propriétaire les 19 et 21/10 :

- **Pas de sessions.** le propriétaire ne met jamais de point final et passe d'un sujet à l'autre, parfois en parallèle.
  Le flux de toutes les sources est découpé en **fils** (sujets de travail ou de vie), qui traversent les sessions et
  les runtimes. Une session Codex puis une session Claude Code sur le même chantier forment un seul fil. À l'inverse,
  une session qui dérive de sujet en contient plusieurs.
- **Un contexte dynamique.** Le contexte est recalculé à chaque message de le propriétaire, selon ce dont ce message a
  besoin, puis reste stable pendant le tour (la boucle d'outils de l'agent), pour que le cache serve.
- **Une compression sans perte silencieuse.** L'historique est réduit à sa forme la plus utile pour le budget.
  L'original reste récupérable. Les consignes de le propriétaire ne sont jamais perdues sans refus explicite.

Hors périmètre pour l'instant (le propriétaire, 21/10) : Telegram et la voix, le runtime Walter, le Guardian. Ils réutiliseront
le même chemin, sans rien reconstruire.

## 1 bis. walter-context comprend l'intention (le propriétaire, 21/10)
walter-context est le premier à lire un message, et c'est lui qui doit **comprendre l'intention de l'input**,
dans sa conversation et pas isolément. Un seul appel au modèle de décision répond à cinq questions :
- **le fil** : lequel, ou un nouveau ;
- **l'acte** : nouveau, suite, validation, correction ou information ;
- **le plan de contexte** : rien, le dernier échange, le fil, ou le fil plus la mémoire ;
- **le niveau** : L1, L2 ou L3 ;
- **la famille de tâche**, prise dans les tâches du Router.

Le Router reçoit cette intention pour choisir le modèle, au lieu de reclasser le message seul : un « et demain ? »
est incompréhensible sans sa conversation. L'**intention initiale** de chaque fil (son objectif) est gardée en tête de
son carnet, et la compression ne peut pas la perdre.

## 2. Qui fait quoi
| Module | Rôle |
|---|---|
| **walter-context** | Le chemin de chaque message, le budget, le cache et les ports des harnesses. Seul responsable de l'assemblage du payload |
| **Walter Memory** | Propriétaire des **fils** et des **carnets** : données dérivées, révisables, avec sources et classe de confidentialité. Mis à jour après chaque tour, par le bus. Écriture par sa porte unique. Le carnet de fil remplace la synthèse par conversation (L3) |
| **walter-logs** | Le journal brut, tous runtimes : extraits mot pour mot d'un fil, originaux des sorties compressées |
| **Walter Router** | Désigne le modèle de décision, le reranker et le petit modèle rédacteur du carnet. Aucun modèle n'est écrit en dur |
| walter-soul, walter-skills | Fournissent le contenu (identité, procédures). walter-context les place |

Interconnexion : walter-context lit Walter Memory par sa bibliothèque publique ou sa passerelle. Memory atteint
walter-context par la commande `walter-context` ou le bus, jamais par son dossier.

## 3. Le payload
Les couches sont empilées de la plus stable à la plus changeante. Un seul budget, réglé par profil de modèle, les
partage.

```
tête         identité, règles, outils            ne change presque jamais    ← en cache
session      fils actifs, carnet du fil           change aux frontières       ← en cache
historique   tours passés, compressés             ne fait que s'allonger      ← en cache
tour         contexte dynamique de ce message     change à chaque message
vivant       le tour en cours, mot pour mot
```

Les marqueurs de cache sont placés selon le fournisseur : préfixe automatique (OpenAI, DeepSeek…) ou points
explicites (Anthropic, quatre au plus).

## 4. Le cycle d'un message
```
1. SENTIR      local, ~20 ms, gratuit      embeddings locaux (potion) + entités + récence
                                           → 5 fils candidats, souvenirs candidats
2. COMPRENDRE  modèle de décision        l'intention : quel fil (ou nouveau) · acte · plan de contexte
               (Router, ~0,6 s)            (aucun / dernier échange / fil / fil + mémoire) · niveau · tâche.
                                           Une réponse courte moins de 2 h après fixe le fil sans attendre
3. RÉUNIR      selon le plan               carnet du fil + derniers échanges (walter-logs, tout runtime)
                                           + mémoire (reranker seulement si les candidats dépassent le budget)
4. COMPOSER    stable → changeant          couches, budget, marqueurs de cache
5. COMPRESSER  pendant le tour             le moteur de compression
6. APPRENDRE   après le tour (Memory)      rattacher l'échange, mettre le carnet à jour, événement sur le bus
```

Ce que chaque brique apporte, et où elle ne sert pas :
- **Embeddings locaux** : la présélection, à chaque message. Gratuits, quelques ms, utilisables aussi sur les données
  privées. Gemini Embedding 2, premier du Router, n'apporte rien ici : 0,4 s, un appel cloud et la revectorisation de
  290 000 passages, pour un tri que la décision affine de toute façon.
- **Modèle de décision** (API Decisions : questions fermées, une probabilité par option) : comprendre l'intention,
  c'est-à-dire trancher le fil, le nouveau sujet, l'acte, le plan de contexte, le niveau et la tâche. En cas de doute entre deux fils, on donne les deux au lieu de deviner. Il ne
  rédige rien.
- **Reranker** : choisir parmi beaucoup de souvenirs quand le budget est serré (réparation de la mémoire du 19/10 :
  réponse juste 11 → 29 sur 30). Il est inutile pour le choix du fil. Seulement sur des données `cloud_allowed`.
- **Petit modèle rédacteur** : le carnet, en arrière-plan. Les faits (fichiers, commandes, commits, services) sont
  relevés sans modèle. Seuls les consignes, décisions et points ouverts passent par lui.

Ordres de grandeur par message : environ 0,00003 $ de décision, plus 0,002 $ si on reranke, plus une fraction de
centime pour le carnet. Moins de 1,5 s au pire, rien quand la décision est évidente (le hook actuel prend 0,6 s).

Confidentialité : `local_only` (profil wild, Beeper non pseudonymisé) n'utilise que le local (embeddings, règles).
`redacted_cloud` est pseudonymisé par `walter_memory.llm`. Un agent cloud ne reçoit jamais de contenu `local_only`.

## 5. Le moteur de compression (`compress`)
Acquis du 11/10, conservés :
- **Le journal est la vérité, le payload une projection.** Chaque zone (`head | record | compact | live`) est une
  fonction pure de ce qu'elle couvre.
- **Les coupures n'avancent que vers l'avant.** Entre deux frontières, le payload ne fait que s'allonger. À une
  frontière, ce qui était déjà compacté se rend aux mêmes octets, donc le préfixe reste en cache.
- **Les frontières sont chiffrées** par profil de modèle (coûts caché/écrit, TTL, appels par tour). Au-delà du budget
  effectif, la qualité prime.
- **Une sortie compactée garde sa référence** (identifiant d'appel), relue par `walter-context recover`.

Fait au lot 2 (21/10, context e4b4f1a) :
- **Un seul relevé pour les deux contrats d'hôte.** La projection (Hermes, l'hôte garde son historique) et le
  checkpoint (DSH, l'hôte conserve le relevé) rendent le même relevé : chaque message de le propriétaire et chaque texte visible
  de l'assistant mot pour mot et dans l'ordre, chaque action avec son statut et sa référence. Les injections de Walter
  (`<memory-context>`…) ne sont pas recopiées : ce ne sont pas les mots de le propriétaire.
- **Une échelle commune.** Sorties d'outils → condensé + référence ; raisonnement → pas rejoué ; tours anciens → une
  ligne, la demande de le propriétaire restant entière ; un tour n'est retiré que si même une ligne par tour dépasse toute la
  part du relevé, et le relevé le dit. Le checkpoint garde sa règle plus stricte : refus si le dialogue complet ne tient
  pas.
- **Avant le lot 2**, la projection coupait la demande de le propriétaire à 1 200 caractères, puis pouvait la réduire à une
  ligne ou l'omettre. **Coût mesuré** sur les 21 chaînes A8 (1 137 appels) : 58,4k → 59,6k tokens par appel (+2 %),
  3 358 → 3 375 hors cache.
- **Acceptation étendue** : vos messages restent visibles à 100 % dans la projection, à ses deux niveaux. 14 cas sur
  14, 5 refus attendus.
- **Reporté au lot 4 (compose)** : les marqueurs de cache par fournisseur. Hermes place aujourd'hui les siens
  (`prompt_caching`). `context_recover` est déjà exposé au modèle dans les deux ports.
- **Plus tard (lot 6)** : compression par fil. Les tours du sujet en cours restent mot pour mot, ceux des autres
  sujets passent à une ligne et reviennent si le propriétaire y revient.

## 6. Selon le harness
| Harness | Ce que walter-context peut faire |
|---|---|
| Hermes | Tout : le port `ContextEngine` remplace le compresseur natif (lot 6) |
| DSH | Tout, par son contrat de compaction (actif). Passe au moteur unifié au lot 2 |
| Claude Code | Ajout seulement : contexte dynamique par le hook de chaque message, carnet réinjecté après chaque compaction native |
| Codex | Ajout seulement : hook `notify`, consignes, MCP |

## 7. Mesures disponibles
- **C0, rejeu (11/10)** : à périmètre égal (21 chaînes A8), 57,8k tokens par appel contre 71,9k pour Hermes réel,
  −23 % de coût. Relancé le 21/10 sur 5 sessions récentes (1 460 appels) : 46k tokens par appel contre 149k sans
  compression (31 % du coût).
- **Acceptation** : 14 cas synthétiques, rétention exacte, 5 refus attendus. Identique avant et après le lot 0 :
  9 532 tokens rendus, au token près.
- **T0, fils (21/10)** : référence de 156 échanges (14→21/10, Claude Code, Codex, Hermes) annotée en 21 sujets, dans
  l'instance (`state/context/threads-gold-20261014.json`, privé).
  - Constat : **les sessions ne sont pas des sujets.** « Accès Bitwarden » passe à la facture Google, au Router, puis
    aux codes OTP, et deux sessions tournent en parallèle.
  - Tri local seul : au mieux un rattachement juste sur deux, et 7 nouveaux sujets détectés sur 21. Il ne suffit pas
    à décider.
  - En présélection, en revanche, le bon fil est parmi les 5 candidats dans 95 % des cas (θ 0,40). D'où l'étape
    DÉCIDER.

- **Lot 1, intention (21/10)** : mêmes 156 messages, annotés aussi par acte et par plan de contexte (dans l'instance).
  Un appel par message, 4 modèles, 0,21 $ au total. Résultats (mode flux / mode session) :

  | Modèle | Fil juste | Nouveau sujet | Réponses courtes | Acte | Plan | Latence p50 / p95 |
  |---|---|---|---|---|---|---|
  | **d1-ultra** | 77 % / **81 %** | 7/21 | **33/36** | 79 / 81 % | **67 / 61 %** | 0,6 / 1,2 s |
  | Clef (gratuit) | 75 / 77 % | 6/21 | 25-31/36 | **82 / 79 %** | 65 / 66 % | 0,5 / 1,0 s |
  | Jev (en place) | 77 / 71 % | 7-9/21 | 26-31/36 | 76 / 77 % | 39 / 37 % | 0,5 / 0,6 s |
  | Mercury (gratuit) | 74 / 74 % | 9-10/21 | 29-31/36 | 69 % | 48 / 45 % | 0,5 / 1,0 s |

  Le tri local seul était à 57 %. Le banc existant du Router (30 demandes isolées) donnait 30/30 à tous : comprendre
  un message seul ne départage rien, le comprendre dans sa conversation si. Erreur de plan dominante (prudente) :
  « fil » au lieu de « dernier échange », ce qui coûte des tokens sans rien perdre. Point faible commun : la détection
  d'un nouveau sujet. Les fiches de fil du banc ne sont que des mots-clés ; les vraies fiches (titre, objectif,
  carnet) du lot 3 et une question dédiée « nouveau sujet ? » sont les leviers.
  Recommandation : d1-ultra pour l'intention, Clef (gratuit) en repli.
- **Analyse des erreurs de d1-ultra (21/10, deuxième passage avec le détail de chaque décision).**
  - Écart d'un passage à l'autre : ±5 à 8 points. Le modèle n'est pas déterministe, et une erreur de rattachement
    change les candidats suivants.
  - Mode flux : suite d'un sujet juste 117/135 ; nouveaux sujets détectés 7/20 ; plan insuffisant 11/156 (le reste
    des erreurs de plan donne trop de contexte, ce qui est sans gravité).
  - La confiance renseigne sans suffire : ≥ 0,9 → 89-94 % juste ; < 0,7 → 65-82 %.
  - Donner les deux premiers fils en cas de doute aide peu (117 → 121) : les erreurs ne sont pas des seconds choix.
  - **Filet de sécurité retenu** : garder toujours les 3 derniers échanges du canal. Le bon contexte est alors
    visible dans 129/135 cas (96 %). Avec un plancher de plan (au moins le dernier échange s'il date de moins de
    30 min), les plans insuffisants passent de 11 à 9.
  - Seuils visés avant Telegram ou la voix : bon contexte visible ≥ 98 %, nouveaux sujets ≥ 80 %. Leviers : vraies
    fiches de fil (lot 3), filet des derniers échanges, plancher de plan, escalade vers un modèle plus fort quand la
    confiance est basse, recoupage nocturne des fils.
  - Dans Claude Code et Codex, l'historique natif reste là : une erreur n'ajoute que du bruit et ne fait rien perdre.
    80 % suffit pour y démarrer en fantôme.

- **Les cinq solutions (21/10, le propriétaire : « on essaye les 5 »).** Quatre configurations, chacune dans les deux
  modes, avec d1-ultra ; les fiches et l'escalade passent par les postes `memory_extraction` et `general` du Router
  (abonnement Codex, gpt-6-luna). Seuls les effets nets et répétés comptent (écart entre passages : ±5 points).

  | Solution | Effet | Retenue |
  |---|---|---|
  | 1. Toujours les 3 derniers échanges du canal | bon contexte visible 74 → 92 % (flux), 84 → 96 % (session) | oui |
  | 2. Plancher : au moins le dernier échange s'il date de moins de 30 min | plan insuffisant 14 → 11 | oui |
  | 3. Vraies fiches de fil (titre, objectif initial, état, dernière étape) | nouveaux sujets 8 → 10-11/21, F1 0,62 → 0,70 | oui |
  | 4. Escalade vers un modèle plus fort si confiance < 0,7 (~30 % des messages) | fil : pas mieux ; plan insuffisant ÷ 2 | pour le plan seulement |
  | 5. Nuit v1 (un appel regroupe toutes les fiches) | regroupe par domaine : 21 sujets → 12 fils | non ; v2 par paires en test |

  Tout combiner est moins bon que les parties : l'escalade défaisait le gain des fiches sur le choix du fil.
  Combinaison retenue (fiches + filet + plancher + escalade du plan seul), passée deux fois à l'identique : le fil juste
  varie de 72 à 82 % d'un passage à l'autre. L'écart entre passages est aussi grand que l'effet des solutions. Ce qui
  tient d'un passage à l'autre :
  - bon contexte visible : 88-96 % ;
  - plan insuffisant : 11 → 6-8 ;
  - F1 du découpage : jusqu'à 0,72.

  Nuit v2 (fusion paire par paire, oui ≥ 0,8 ; ré-attachement) : aucune fusion, aucun déplacement. Le découpage de
  jour n'est pas trop fragmenté (21 fils pour 21 sujets en mode flux) : les erreurs sont des mauvais rattachements, pas
  des doublons. Elle est gardée en réserve, sans priorité.

  Conception retenue pour COMPRENDRE (lot 4) :
  - d1-ultra, avec les fiches de fil ;
  - les 3 derniers échanges toujours inclus ;
  - le plancher de plan ;
  - escalade du seul plan vers le poste `general` quand la confiance est < 0,7 ;
  - **dernier filet** : le tableau des fils actifs (une ligne chacun) est toujours dans le payload, et le modèle
    principal peut ouvrir un fil lui-même (outil `thread_open`). walter-context n'a pas à être parfait : il propose,
    le modèle principal, bien plus fort que d1-ultra, corrige.

  Coût de la soirée : 0,26 $ OpenRouter (décisions), plus le quota de l'abonnement Codex pour les fiches et
  l'escalade.

## 8. Plan
| Lot | Contenu | Critère de réussite | Accord de le propriétaire |
|---|---|---|---|
| **0. Fondations** ✅ 21/10 | `/walter/context`, sous-module `compress`, `recover`, banc des fils, contrat 1.1.0, module neutre, CLI sur le PATH | Tests verts (27 Python + 9 DSH), acceptation identique, `walter check` vert | — |
| **1. Comprendre l'intention : mesures** ✅ 21/10 (reranker : au lot 4) | Fil, acte, plan, niveau et tâche en un appel, 4 modèles, sur la référence T0 annotée | d1-ultra recommandé, Clef en repli ; voir §7 | fait, 0,21 $ |
| **2. Moteur de compression unifié** ✅ 21/10 | Un seul calcul, l'échelle, l'ordre de sacrifice, le refus explicite, les marqueurs de cache par fournisseur, `recover` visible du modèle | Rejeu au moins aussi bon qu'aujourd'hui, 14 cas d'acceptation verts, DSH dessus | non |
| **3. Fils et carnets** (Walter Memory) | Tables des fils, membres (renvois vers walter-logs) et carnets (ajout seul). Rattachement après chaque tour (bus). Carnet : faits sans modèle, consignes et décisions par le petit modèle. Rattrapage depuis le 14/10, fusion et scission la nuit | ≥ 85 % de rattachements justes sur T0. « Qu'a fait le propriétaire via Codex le 17-18/10 ? » retrouve les deux chantiers | oui (structure mémoire, à faire avec le chantier mémoire) |
| **4. Contexte dynamique** | sense · decide · gather · compose, d'abord en fantôme (calculé, journalisé, sans rien injecter), puis il remplace l'injection fixe du hook (Claude Code, Codex) et réinjecte le carnet après la compaction native | Plans justes sur la référence, p95 < 1,5 s, plus d'injection hors sujet | oui (bascule du hook) |
| **5. Qualité** | Comparer les réponses avec l'historique complet et avec le payload walter-context, sur de vraies sessions | Aucune consigne perdue, qualité égale ou meilleure | oui (budget) |
| **6. Mise en service Hermes** | Le port remplace le compresseur natif, compression par fil, 7 jours de comparaison A8 | Non caché, latence et qualité au moins égaux | oui |

Ordre : 0, puis 1 et 2 en parallèle, puis 3 → 4 → 5 → 6.

## 9. Décisions et points ouverts
- 21/10 (le propriétaire) : walter-compress est retiré de Hermes (il n'a plus d'intérêt). Les fils et les carnets
  appartiennent à Walter Memory, et le carnet remplace la synthèse L3. Validé avec le plan.
- À trancher :
  - route du petit modèle et du banc de qualité (proposé : abonnement Codex par walter-llm, plutôt que recharger
    OpenRouter) ;
  - d1-ultra contre Jev au poste « decision » du Router (le lot 1 le chiffrera) ;
  - sort des « Guardian review » de Codex dans la mémoire (proposé : revues d'agent, exclues de « ce que le propriétaire a
    dit »).
- Le hook mémoire actuel injecte à chaque message avec un budget fixe. Exemple du 21/10 : des souvenirs sur Scena,
  injectés pour une question sur ce plan. Le lot 4 le corrige.
