# walter-context

| | |
|---|---|
| **Rôle** | Préparer et ordonner le contexte par message et par sous-agent, et compresser l'historique selon le contrat du harness. |
| **Propriétaire** | walter-context (`/walter/context`). |
| **État** | **active** (constat du 09/11/2026) : service `walter-context-preflight` ; DSH l'utilise ; Hermes garde son compresseur natif jusqu'au lot 6. |
| **Ne fait pas** | Posséder les sujets, vues et originaux (Walter Memory, walter-logs) ; choisir un modèle (Router). |
| **Contrats** | [contracts/context.json](contracts/context.json), [contracts/maintenance.json](contracts/maintenance.json), [contracts/schemas/](contracts/schemas/) (ContextPlan v2, ChildContextSpec v1) ; CLI `walter-context`. Spécification : `/walter/docs/CONTEXT-ENGINE.md`. |

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
les anciens tours et, si le budget l’impose, signaler l’omission de tours. Le checkpoint DSH exige de conserver
le dialogue visible complet ou refuse la compression. Une référence permet de demander un original lorsqu’il est
encore disponible et autorisé ; elle ne rend pas ce contenu visible automatiquement dans chaque requête.
Les injections des tours précédents ne sont pas recopiées comme des paroles de l’utilisateur.

Les tests structurels et à réponses attendues vérifient la présence de preuves et les refus. Ils ne certifient pas
la qualité sémantique générale des réponses, le cache réel d’un fournisseur ou la compréhension multimodale.

## Ports et activation

| Port | Contrat | État connu et portée |
|---|---|---|
| DSH | Transaction publique de compaction, checkpoint | Port sélectionné dans la configuration observée le 29 octobre 2026 ; chargement à confirmer par lancement/trace |
| Hermes | `ContextEngine`, projection | Adaptateur disponible ; configuration observée : compresseur natif, port Context non activé |
| Codex et Claude Code | Compaction native ; contexte additionnel via hook/MCP | Notes de modules et preflight disponibles ; aucune substitution du compresseur natif |
| Claude Code, entrée des sorties | Hook PostToolUse → `walter-context-entrance` (`updatedToolOutput` à terme) | **Fantôme** depuis le 6 novembre 2026 : enregistre ce qu’il aurait coupé (chiffres seulement) ; la sortie reste entière pour le modèle |
| Hook DSH | Pack par message via le service de preflight | Mode `legacy` par défaut ; mode `pack` uniquement par interrupteur d’instance ou variable d’expérience |
| Router, sous-agent texte | `walter-context-child` | Construction du pack appelée par Router ; le mode et le comportement en échec sont définis côté consommateur |

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
