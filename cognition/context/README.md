# walter-context

| | |
|---|---|
| **Rôle** | Préparer et ordonner le contexte par message et par sous-agent, et compresser l'historique selon le contrat du harness. |
| **Propriétaire** | walter-context (`/walter/cognition/context`). |
| **État** | **active** (27/11/2026) : service `walter-context-preflight` ; le moteur natif Walter Engine (`walter-engine`) l'appelle à chaque message du propriétaire. |
| **Ne fait pas** | Posséder les sujets, vues et originaux (Walter Memory, walter-logs) ; choisir un modèle (Router). |
| **Contrats** | [contracts/context.json](contracts/context.json), [contracts/maintenance.json](contracts/maintenance.json), [contracts/schemas/](contracts/schemas/) (ContextPlan v4 — v3, v2 et v1 gardés, ChildContextSpec v1), [manifest/decisions.json](manifest/decisions.json) (signaux de décision déclarés) ; CLI `walter-context`. Spécification : `/walter/cognition/context/docs/CONTEXT-ENGINE.md`. |

walter-context prépare ce qui entre dans la fenêtre d’un modèle et compresse l’historique selon le contrat du
harness. La compression locale, la préparation d’un contexte par message et le contexte d’un sous-agent sont des
fonctions distinctes. Elles sont implémentées ; leur présence ne prouve pas leur activation dans un processus.

Les sujets, vues et originaux appartiennent à Walter Memory/Logs. Context les lit par leurs interfaces publiques ;
il ne possède pas leurs données canoniques. Le preflight peut rattacher son plan au run via `walter-memory runs
update`. La cible de continuité entre sessions et runtimes reste une direction d’architecture, pas une garantie
que les sessions ont disparu de tous les ports.

[Maintenance, dépendances, activation et retrait](docs/MAINTENANCE.md) ·
[Contrat du module](contracts/context.json) · [Validation de rétention](docs/ACCEPTANCE.md).
La spécification et les décisions propres à une instance restent dans sa documentation, hors du logiciel neutre.

## Parcours d'un message du propriétaire (moteur natif, état du 27/11/2026)

Qui décide de quoi, dans l'ordre. Cette section suffit pour expliquer l'architecture ; le code n'est à relire que
pour un détail qu'elle ne donne pas. Sources : `walter_context/preflight/` (`__main__.py` service, `__init__.py`
décision), `retrieval.py` (blocs), `assembly.py` (pack) ; côté moteur `core/engine/walter_engine/engine.py`
(`_intake`), côté modèle `cognition/router/llm/gateway.py` (`planned_task`).

1. **Engine** (`walter-engine`) reçoit le message d'une porte (Telegram, web, API), ouvre le **run** au Run Plane de
   Memory (`runs start`) et lance en parallèle la recherche de skills. Un run `local_only` s'arrête là pour le
   contexte (pas de préflight cloud).
2. Engine appelle le **préflight** (`POST 127.0.0.1:8897/preflight?inject=1`) avec le message, **l'échange
   précédent visible** de la session (dernier message et dernière réponse, avec leur âge et leur fil s'il y en a
   un) et l'identifiant du run ; il attend au plus 7 s (`answer_within_ms`).
3. Le préflight cherche les **fils candidats** (sujets de Memory proches) et démarre en avance les sources qui ne
   dépendent que du message (`Prefetch`).
4. **Règles déterministes d'abord** (`fast_path`) : réponse courte à un fil récent (« ok », « vas-y »), question
   triviale (heure, date : répondue sans modèle).
5. Sinon **Walter Decision** : un appel au **poste de décision du Router** (pas au modèle principal) pose en une fois
   les signaux déclarés dans `manifest/decisions.json` et ceux de Router et Memory : acte (par rapport à
   l'échange visible), fil persistant (par rapport aux fils stockés — deux questions distinctes : une suite peut
   continuer la conversation sans rejoindre aucun fil), plan de lecture, besoins personnels, palier de modèle
   (L1/L2/L3), travail à suivre, reprise de tâche, lectures (dates, personnes, lieux). Le **résolveur** applique
   ensuite les relations déclarées (par ex. acte `new` ⇒ fil `new`) et met de côté une réponse incohérente.
6. Le préflight en tire le **ContextPlan** : niveau de contexte L0–L4 (profondeur de récupération), acte, fil,
   effort du tour, et `model_profile` = **toujours `general`** au palier jugé (un spécialiste est un sous-agent que le
   modèle principal choisit, jamais un remplacement du modèle du tour).
7. En parallèle : il **rattache le plan au run** (`walter-memory runs update` : fil, acte, `requested` {task, level,
   work, resume}) — c'est là que le Run Plane ouvre ou reprend un objectif durable — et il **assemble le pack** :
   les blocs que le plan demande (`retrieval.gather`), chacun seulement s'il est pertinent. Un niveau ne remplit pas
   tous les blocs : l'état de travail de la session n'entre que si le message continue ce fil ou cet échange, les
   autres objectifs que pour une demande qui touche aux tâches (`personal` contient `tasks`), filtrés par canal
   (test ≠ propriétaire). Ordre : stable avant volatil ; budget par niveau (`[pack] budget`), coupes dites.
8. Engine place le pack `<walter-context>` avant le message dans son historique. Les packs des tours précédents
   sont remplacés par un talon dans l'historique (`[native] past_packs = "stub"`) : seul le pack du message actuel
   vaut, l'original reste lisible avec `context_recover(ref="pack:<seq>")`.
9. **Modèle du tour** : Engine appelle `walter-llm` avec le run ; le gateway lit `requested` sur le run et choisit
   la tâche Router `general/<palier>` (`planned_task`) ; le **Router** résout ce poste en modèle et fournisseur
   concrets (tables du Router, jamais codées dans Context ni dans Engine). Le même plan vaut pour tous les appels du
   tour ; un palier épinglé par le propriétaire l'emporte.
10. Pendant le tour, Context garde l'état vivant (`state`) et ne réévalue qu'en cas de déclencheur (`reassess` :
    échec, réponse d'un sous-agent, fin de tâche), jamais un préflight complet ; la fenêtre envoyée au modèle est
    projetée par `compress` (`head → record → compact → live`).

En échec ou hors délai : plan dégradé déclaré (voir plus bas), jamais un silence.

## Composants présents

| Composant | Responsabilité | État et limite |
|---|---|---|
| `compress` | Projection `head → record → compact → live` et checkpoint | Implémenté ; contrats différents selon le host |
| `recover` | Lire les originaux associés aux références de sortie d’outil | Implémenté ; dépend de la disponibilité et de la confidentialité du journal source |
| `config` | Charger la politique de compression, les profils et les notes de capacités | Implémenté ; des budgets de retrieval/child restent des constantes dans leur code |
| `bridge` | Protocole JSON version 1 hors processus pour les ports | Implémenté ; plan, summarize et capability |
| `plan`, `preflight` | Produire un ContextPlan : sujet, acte, niveau, capacités et profil demandé au Router | Implémenté ; règles locales puis décision routée quand nécessaire, repli local L1 |
| `retrieval` | Récupérer présentations de modules, vues, mémoire, registres et échanges selon le plan | Implémenté ; une source en échec retire son bloc et ajoute une note |
| `assembly` | Ordonner les blocs stables avant les blocs volatils et compter l’injection | Implémenté ; ajoute du contexte sans remplacer l’historique natif du host |
| `state`, `reassess` | État vivant d'une session (WorkingState) mis à jour par événements, réévaluation ciblée en cours d'exécution | Implémenté (17/11) ; routes `/v1/state*` et `/v1/reassess` du service preflight, état sous `<instance>/state/context/working/` ; la mémoire reste la vérité |
| `decision_state` | Ce sur quoi une décision se prend : observé / déduit, connu / cherchable / non consulté / manquant, contradictions, contraintes | Implémenté ; branché au preflight derrière `[state] decision_state` (éteint par défaut) |
| `longtext` | Représentation d'un long message du propriétaire (début, fin, phrases à consigne / négation / date / montant, plages omises dites) | Implémenté ; actif par défaut (`[longtext]`), remplace la coupe à 1 500 caractères |
| `child` | Préparer mission, capacités, suggestions de skills, sujet, observations et mémoire d’un sous-agent | Implémenté ; sources optionnelles isolées, contexte de l’appelant conservé |

Les anciens noms de plan `sense`, `gather` et `compose` ne désignent pas trois sous-modules à construire : la
sélection des sujets est fournie par Memory, la récupération est dans `retrieval`, la composition dans `assembly`.
Le routage des modèles concrets reste la responsabilité de Router.

## Compression et récupération

```text
payload = head | record | compact | live
```

Le journal reste la référence ; le payload en est une projection. Les coupures avancent et les zones déjà
compactées gardent une représentation stable entre coupures. La politique évalue budget et coûts relatifs de
cache ; ces estimations ne sont pas une mesure de facturation fournisseur.

La projection peut remplacer des sorties d’outils par un digest et une référence, omettre le raisonnement, réduire
les anciens tours et, si le budget l’impose, signaler l’omission de tours. Le checkpoint (port DSH, historique) exigeait de conserver
le dialogue visible complet ou refusait la compression. Une référence permet de demander un original lorsqu’il est
encore disponible et autorisé ; elle ne rend pas ce contenu visible automatiquement dans chaque requête.
Les injections des tours précédents ne sont pas recopiées comme des paroles de l’utilisateur.

Les tests structurels et à réponses attendues vérifient la présence de preuves et les refus. Ils ne certifient pas
la qualité sémantique générale des réponses, le cache réel d’un fournisseur ou la compréhension multimodale.

## Ports et activation

| Port | Contrat | État connu et portée |
|---|---|---|
| Codex et Claude Code | Compaction native ; contexte additionnel via hook/MCP | Notes de modules et preflight disponibles ; aucune substitution du compresseur natif |
| Claude Code, entrée des sorties | Hook PostToolUse → `walter-context-entrance` (`updatedToolOutput` à terme) | **Fantôme** depuis le 6 novembre 2026 : enregistre ce qu’il aurait coupé (chiffres seulement) ; la sortie reste entière pour le modèle |
| Walter Engine (`walter-engine`, natif) | Pack par message : `_intake` du moteur → `POST /preflight?inject=1` ; fenêtre du tour par `compress` | **En service** depuis le 17/11/2026 : `pack` par défaut ; bloc Memory `legacy` seulement si le preflight échoue ou dépasse 7 s. (Jusqu'au 17/11 : greffon d'entrée de DSH, désinstallé le 18/11 ; port `ports/dsh/` = retour arrière seulement.) |
| Router, sous-agent texte | `walter-context-child` | Construction du pack appelée par Router ; le mode et le comportement en échec sont définis côté consommateur |

Plan dégradé (SOCLE A2, 11/11/2026) : si la décision échoue, le plan le dit (`decision.degraded`, `decision.error`),
reste prudent (L3, `tools` + `memory`, sujet le plus proche par embeddings locaux, profil du tour précédent de la
session s’il a moins de 30 min sinon `general/L2`), ouvre le pack par une phrase qui le signale au modèle, émet
`context.degraded` sur le bus et est compté à part par `--report`. Le pack a un budget total par niveau et des blocs
Tâches / Expérience (routes Memory `/v1/tasks/list`, `/v1/experience`) : section `[pack]` de la configuration ; les
tâches du fil et un échec récent entrent dans le pack à tous les niveaux, L0 compris (12/11/2026) ;
les autres objectifs actifs seulement quand la réponse dépend des tâches du propriétaire, du seul canal de la session (27/11/2026). Le preflight juge
aussi si le message est un travail à suivre (`decision.work`) : c'est ce qui ouvre une tâche durable au Run Plane.
Une approbation ou une correction (`act` = `approve` / `correct`) envoyée moins de 30 min après un échange reste dans
le fil de cet échange (`decision.thread_by = previous_exchange`, le choix du modèle en `thread.alternates`) ; le fil
du dernier tour est désigné au modèle de décision, et une hésitation sans majorité y laisse la conversation.
**Trois dimensions indépendantes** (27/11/2026, Monsieur) :
- la **profondeur de contexte** L0–L4 (`level`, Context) vient du seul plan. L4 = le sujet plus une mémoire qui remonte
  à des mois ou des années (plan « fil + mémoire », horizon « long ») ;
- le **palier de raisonnement** L1–L3 (`model_profile.level`, le Router) ;
- le **budget d'exécution** L0–L4 (`decision.effort`, le moteur, qui en tire les plafonds du tour). Il vient du palier,
  et passe à L4 pour un travail à mener (`work`) ou une recherche approfondie (`extensive`), sans jamais dépendre du
  niveau de contexte. Une recherche externe approfondie a donc L4 sans mémoire personnelle, et une question simple
  qui demande de fouiller la mémoire garde son budget.

La mémoire nécessaire (`needs` = memory) donne le bloc mémoire à tout niveau, sans les fils : la règle qui la
liait au plan « fil + mémoire » est retirée. Un goût du propriétaire, seul (`personal` = preferences), donne une
recherche ciblée (`[pack.memory_budget.targeted]`).
**Réponse dans le délai de l'appelant** (13/11/2026) : l'appelant dit combien de temps il attend
(`answer_within_ms`, 7 s pour le moteur et le hook) ; le preflight répond avant (`[preflight] answer_within_s`,
`answer_margin_s`). Les sources du pack sont interrogées ensemble (le pack coûte sa source la plus lente, pas leur
somme) et le run est rattaché pendant ce temps. Une source pas prête à l'échéance est laissée de côté, notée
(`pack.late`, `notes`) et **dite au modèle** en tête du pack (« Contexte incomplet : … ») ; une décision pas rendue à
temps (`pack_reserve_s` avant l'échéance) donne le plan dégradé déclaré, jamais une absence de réponse. Chaque ligne
du journal porte `total_ms`. La décision elle-même reçoit le temps dont dispose l'appelant (et non plus 15 s fixes).
**Reprise d'une tâche** (13/11/2026) : quand un fil candidat porte une tâche ouverte ou suspendue (champ `task` de sa
carte, ou carte de genre `task`), le preflight juge aussi si le message la reprend (`decision.resume`, question posée
seulement dans ce cas) ; ≥ 0,5 → `requested.resume` au Run Plane, qui rattache le run à la tâche du fil au lieu d'en
ouvrir une autre — une reprise depuis une autre interface n'a pas d'échange précédent, son acte revient « new ».
**Plan dégradé et fil** : sans jugement du modèle, moins de 30 min après un échange, la conversation reste dans le fil
de cet échange (`thread_by = previous_exchange`) ; au-delà, le sujet le plus proche en mots, s'il l'est assez.
**Questions composées depuis le registre** (Walter Decision 2.0, 17/11/2026, `[preflight] signals = "registry"` ;
`"questions"` = le jeu 2 d'avant, retour arrière immédiat) : le preflight ne tient plus sa liste de questions ; il
demande l'occasion `turn` avec ses faits (`threads`, `open_task`) et ses options (les fils candidats), et Walter
Decision compose les signaux que Context, Router et Memory déclarent dans leur `manifest/decisions.json` (acte, plan,
domaine, horizon, besoins en une question à plusieurs options, palier, travail, reprise, et deux lectures : dates et
personnes nommées). Les réponses reviennent par identifiant de signal ; le plan garde les mêmes champs (contrat
ContextPlan inchangé pour ses consommateurs) et ajoute, à part des jugements, `observations` (v3) : les dates du
message telles qu'écrites + le jour que Walter lit (jamais celui que le modèle devine ; ambiguïté dite) et les
personnes nommées, gardées seulement si le passage est dans le message et lu avec une certitude ≥ 0,5. Ces lectures
nourrissent plusieurs consommateurs sans nouvel appel : le bloc `now` du pack (« Dates du message : … ») et le bloc
`people` (fiches Kardex des personnes nommées, résolues par Memory, une homonymie dite sans nommer les candidats) ;
extraire n'est pas mémoriser (rien n'est écrit). Une lecture qu'aucun modèle de la chaîne ne porte est dite
`unavailable` dans `decision.signals` ; le plan tient sans elle.
**Lectures à part** (`[preflight] readings_apart = true`) : jugements (couche `inference`) et lectures (couche
`observation`, posées sur le seul message, un échantillon) partent en deux appels parallèles ; le plan n'attend que
les jugements, le pack attend les lectures au plus `[pack] readings_wait_s` (borné par l'échéance de la réponse) pour
ses blocs `now` / `people`. Une lecture encore en route quand la réponse part est dite `readings: {late: true}` (rien
n'est perdu en silence). `decision_samples = 2` + `decision_sampling = "first"` : deux échantillons, le premier
arrivé gardé (banc du 17/11) ; `false` / `3` / `"mean"` = le réglage d'avant. Une décision complémentaire ne repose
que ses signaux (`ask` de `POST /v1/decisions`), jamais un préflight complet.
**Préflight natif (18/11/2026)** : la politique du besoin `walter-context-preflight` (Router
`config/decision-needs.json`) dit `assign: "native_whole"` — tout le jeu (jugements, choix multiples, lectures,
images, audio) part en **un** appel au premier modèle de la chaîne qui le porte entier nativement (d1.2-ultra par
l'API Liquid directe) ; un second appel seulement s'il n'a pas répondu en 700 ms ; au-delà de 1,5 s ou sur erreur,
le partage par question d'avant (Drex d'abord) part aussi et la première réponse **complète** gagne
(`decision.assign`, `decision.failover` dans la trace) ; un média qu'aucun autre modèle ne lit (audio) est alors
laissé de côté, pas la question (`media_fallback: "text"`, la transcription est dans le message). Lectures et
jugements voyagent donc ensemble (`readings_apart = false`). Signaux ajoutés au registre de Context : `personal`
(de quoi de la situation du propriétaire la réponse dépend — position, préférences, historique, personnes, projets,
tâches, agenda —, dit ou seulement impliqué), `places` et `amounts` (lectures), `urgency`, `clarity`, `image`
(photo / capture / document) ; relation `personal_needs_memory`. **ContextPlan v4** : `personal`, `assessment`
{urgency, clarity}, `media` {image, audio} ; une image demande `model_profile.require ["vision"]`. Quand `location`
est dans `personal`, le bloc **`position`** (jamais coupé) donne le dernier relevé GPS de Memory
(`walter_memory.whereabouts`) avec son heure : récent, ancien (« il a pu bouger »), absent, ou au domicile connu.
**Médias** (`walter_context/media.py`, `[media]`) : les images et notes vocales que les portes signalent dans le
message (« enregistré ici : … », « audio : … ») ou que l'appelant passe en `attachments` [{type, path}] sont lues
par le modèle de décision lui-même, seulement sous les racines déclarées et sous les tailles limites ; le reste est
dit dans la trace (`media_notes`). Banc : `bench/preflight_native.py` (jeu de référence et résultats dans
l'instance) ; mesures et retour arrière : DECISIONS.md 2026-11-18 « Préflight natif ».

L’état d’un port de compression ne détermine pas le mode d’injection par message. Les essais `pack` ne constituent
pas une décision de migration globale. Voir la maintenance pour les commandes et les modes dégradés.

## Interfaces

```sh
walter-context recover <call-id> [--offset N]
walter-context acceptance
walter-context bench --sessions 40
walter-context quality --samples 30
walter-context threads --gold FILE --mode both
walter-context-preflight --report --days 1
walter-context-entrance --report --days 7
```

`quality` estime par défaut ; `quality --run` et `threads --decide` peuvent appeler un modèle. Le preflight peut
également appeler le modèle de décision via l’interface Memory/Router, et la mémoire récupérée applique sa propre
politique de modèles et de confidentialité. Les jeux de référence privés et les rapports résident dans l’instance.
La compression synthétique `acceptance` n’utilise ni modèle, ni historique privé, ni réseau.

Le service local de preflight expose `GET /health` et `POST /preflight` : réponse ContextPlan,
`?shadow=1` pour enregistrer sans injection, `?inject=1` pour rendre `{plan,text,pack,error}`. Il s’agit d’un port
local de confiance, pas d’une API publique à exposer sur Internet. Le CLI `walter-context-child` reçoit un
ChildContextSpec v1 JSON et retourne `{version,text,summary}`.

## Entrée des sorties d’outils (`compress/entrance`)

Une grosse sortie d’outil est réduite au moment où elle entre dans le contexte, avant que le modèle la lise : début,
fin, lignes « signal » du milieu (erreurs, échecs) avec leur numéro, et l’endroit où relire l’original. Fait à
l’entrée, le cut ne réécrit rien de déjà envoyé : il est sans effet sur le cache. Réglages : section `[entrance]` de
`config/walter-context.toml` (seuil, tailles gardées, outils exemptés, mode). Les sorties que l’hôte a déjà rangées
dans un fichier (`persistedOutputPath` de Claude Code) ne sont pas comptées.

Mode `shadow` : `@instance/state/context/shadow/entrance-<jour>.jsonl` ne contient que des chiffres (outil, tailles,
référence d’appel). Le mode `on` est refusé tant que le hook ne journalise pas lui-même l’original : walter_logs
enregistre le texte que le modèle a vu, une sortie réduite perdrait son original.

## Notes de capacités

`walter-context capability router --tool walter_route --tool walter_run --tool walter_decide --tool walter_plans`
prépare la note versionnée fournie par `walter-router brief --json`. Identité, taille, version et empreinte sont
vérifiées ; si l’inventaire d’outils requis manque, `injection_allowed` est faux. Le host conserve `TurnNotes` et
son snapshot pendant le tour ; un bridge ponctuel ne possède pas cette continuité à lui seul.

`walter-context capability all --tool <name> …` compose la couche « Modules W.Alter » via `walter present notes` :
navigation `module_index`/`module_guide`, présentations et briefs déclarés dans les contrats. Les notes invalides
sont rejetées et le budget `layer_max_chars` est appliqué. `TurnLayer` garde le snapshot du tour. L’option `--write`
écrit `@instance/state/context/modules.md` et demande un rendu des profils lorsque le fichier change ; préparer
une note sans cette option n’active aucun port ni n’injecte dans un host non raccordé.
