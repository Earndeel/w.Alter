# Référence des outils et paramètres

> Généré par `walter-router docs --write`. Modifier les sources, puis régénérer ; ne pas éditer ce fichier.


## walter_route

Examiner un choix et ses routes, sans exécuter la tâche. Pour le texte, provider reflète la première route exécutable ; après exécution, routed.provider indique le fournisseur réel.

| Paramètre | Type | Défaut transport | Obligatoire | Sens et valeurs |
|---|---|---|---|---|
| `request` | string |  | False | Demande à classer ; fournir au moins request, task ou model. La sélection n'exécute pas la tâche.  |
| `task` | string |  | False | Clé de spécialité ; omise = classification par le modèle de décision.  |
| `level` | string |  | False | Niveau fonctionnel du texte général ; les spécialités ont leur classement propre. enum: ["", "L1", "L2", "L3"] |
| `model` | string |  | False | Seulement si l'utilisateur nomme le modèle ; identifiant, alias, nom ou modèle/variante.  |
| `provider` | string |  | False | Avec model, fournisseur expressément demandé : restriction stricte à ce fournisseur. claude-pro désigne le transport d’abonnement Claude du Router, contexte et outils du consommateur.  |
| `require` | string |  | False | Contrainte dure appliquée à la sélection et aux routes ; une seule par appel. enum: ["", "unrestricted", "open_weights", "video_input"] |
| `conversation` | string |  | False | Une ligne sur les échanges précédents pour classer une demande dépendante du contexte. x-note: MCP limite à 600 caractères pour route ; run transmet actuellement sans cette coupure. |

## walter_run

Exécuter une sous-tâche texte ou une génération autorisée ; transmettre user_notice si requis.

| Paramètre | Type | Défaut transport | Obligatoire | Sens et valeurs |
|---|---|---|---|---|
| `request` | string | — | True | Demande originale. Obligatoire dans l'outil MCP ; le CLI accepte goal seul pour le texte.  |
| `goal` | string |  | False | Instructions complètes de la sous-tâche texte ; obligatoire à l'exécution texte.  |
| `context` | string |  | False | Faits, contraintes, extraits et chemins nécessaires à l'exécuteur ; il ne voit pas le chat.  |
| `conversation` | string |  | False | Une ligne sur les échanges précédents pour classer une demande dépendante du contexte. x-note: MCP limite à 600 caractères pour route ; run transmet actuellement sans cette coupure. |
| `task` | string |  | False | Clé de spécialité ; omise = classification par le modèle de décision.  |
| `level` | string |  | False | Niveau fonctionnel du texte général ; les spécialités ont leur classement propre. enum: ["", "L1", "L2", "L3"] |
| `model` | string |  | False | Seulement si l'utilisateur nomme le modèle ; identifiant, alias, nom ou modèle/variante.  |
| `provider` | string |  | False | Avec model, fournisseur expressément demandé : restriction stricte à ce fournisseur. claude-pro désigne le transport d’abonnement Claude du Router, contexte et outils du consommateur.  |
| `require` | string |  | False | Contrainte dure appliquée à la sélection et aux routes ; une seule par appel. enum: ["", "unrestricted", "open_weights", "video_input"] |
| `toolsets` | ["array", "null"] | — | False | Groupes d'outils du texte. Par défaut les capacités Walter (walter-web = walter_browse, skills, memory) via le Tool Gateway ; terminal et fichiers seulement sur demande explicite. items: {"enum": ["web", "walter-web", "file", "terminal", "vision", "skills", "code_execution", "memory"], "type": "string"}; x-effective-default: ["walter-web", "skills", "memory"]; x-note: MCP omet la liste vide ; elle ne désactive donc pas les outils via ce transport. |
| `max_turns` | integer | 0 | False | Nombre maximal d'itérations du texte, appels modèle compris. x-effective-default: 40; x-effective-range: [1, 120]; x-coercion: 0 devient 40 ; bornage 1..120 |
| `budget_seconds` | integer | 0 | False | Budget total texte pour tous les fournisseurs et outils ; une part reste réservée aux fournisseurs suivants. x-effective-default: 900; x-effective-range: [60, 3600]; x-coercion: 0 devient 900 ; bornage 60..3600 |
| `role` | string |  | False | Objectif média, notamment vidéo ; le CLI run ne transmet pas ce champ à la décision texte.  |
| `image_urls` | ["array", "null"] | — | False | URLs de références pour la génération média ; HTTP(S) exigé par MCP. Pas d'attachement automatique au chat texte. items: {"type": "string"} |
| `aspect_ratio` | string |  | False | Format de génération ; valeurs prises en charge selon le modèle et le fournisseur.  |
| `duration` | integer | 0 | False | Durée média demandée, en secondes ; dépend des capacités du modèle.  |
| `resolution` | string |  | False | Résolution média ; la valeur peut être normalisée selon les formats du modèle.  |
| `paid_fallback` | boolean | false | False | Autorise le passage d'un rôle prévu en interface manuelle à une génération payante ; exige la demande de l'utilisateur.  |
| `constraints` | ["object", "null"] | — | False | Contraintes du sous-agent texte ; geo = {zone, pays, devise, langue} pour une recherche locale (la zone est choisie explicitement sur les sites).  |
| `output_schema` | ["object", "null"] | — | False | Forme JSON exigée de la réponse du sous-agent texte.  |
| `persist` | string |  | False | observations = chaque élément de la liste "observations" de la réponse est enregistré comme observation sourcée du run. enum: ["", "observations"] |

## walter_decide

Décision courte, avec options explicites et contexte utile.

| Paramètre | Type | Défaut transport | Obligatoire | Sens et valeurs |
|---|---|---|---|---|
| `question` | string | — | True | Question de décision.  |
| `options` | object | — | True | Nom court → sens de chaque option ; au moins deux options dans MCP. minProperties: 2; additionalProperties: {"type": "string"} |
| `context` | string |  | False | Données sur lesquelles décider.  |

## walter_web

Converser avec un service web de chat activé par le propriétaire (navigateur, sans LLM de Walter) : message, fichiers joints et modèle facultatifs ; réponse verbatim, fichiers produits (images, documents) rendus en chemins locaux. Lent (secondes à minutes) ; seulement quand l'utilisateur demande ce service ou ce qu'il fait seul.

| Paramètre | Type | Défaut transport | Obligatoire | Sens et valeurs |
|---|---|---|---|---|
| `message` | string | — | True | Message envoyé tel quel au service (1 à 20 000 caractères) ; la réponse revient telle quelle.  |
| `service` | string |  | False | Service web conversationnel activé par le propriétaire (table web_services) ; omis = le seul activé.  |
| `model` | string |  | False | Seulement si l'utilisateur le demande : modèle et/ou niveau de réflexion du service, en mots de son interface. Omis = le modèle déjà choisi dans le service, rien n'est changé.  |
| `files` | ["array", "null"] | — | False | Chemins locaux de fichiers joints (10 au plus, 50 Mo chacun). items: {"type": "string"} |
| `conversation` | string | default | False | Nom de la conversation suivie ; même nom = même fil chez le service.  |
| `request_id` | string |  | False | Identifiant idempotent : une relance rend la réponse déjà obtenue, jamais un second envoi.  |
| `timeout_s` | integer | 0 | False | Délai maximal d'attente de la réponse, en secondes. x-effective-default: table web_services (300 pour chatgpt); x-effective-range: [1, 600] |

## walter_plans

Lire les abonnements, ou enregistrer une modification demandée par leur propriétaire.

| Paramètre | Type | Défaut transport | Obligatoire | Sens et valeurs |
|---|---|---|---|---|
| `action` | string | list | False | Lire, enregistrer une déclaration ou retirer un abonnement. enum: ["list", "set", "retire"] |
| `plan_id` | string |  | False | Identifiant obligatoire pour set/retire.  |
| `vendor` | string |  | False | Éditeur déclaré par l'utilisateur.  |
| `plan` | string |  | False | Nom du forfait déclaré.  |
| `price_usd_month` | ["number", "null"] | — | False | Prix mensuel en USD, uniquement sur déclaration ou preuve validée.  |
| `models` | ["array", "null"] | — | False | Identifiants des modèles inclus ; ne pas les inventer. items: {"type": "string"} |
| `since` | string |  | False | Date déclarée de début, YYYY-MM-DD.  |
| `until` | string |  | False | Fin déclarée d'une offre, YYYY-MM-DD.  |
| `note` | string |  | False | Précisions sur l'abonnement.  |
| `why` | string |  | False | Provenance ou raison de la déclaration, conservée dans l'historique.  |

## CLI complète

```text
walter-router alerts
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  --all :  ; défaut=false
walter-router alias-add
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  key :  ; défaut=—
  model_id :  ; défaut=—
  --reason :  ; défaut=—
  --origin :  ; défaut=agent
walter-router alias-list
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
walter-router alias-remove
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  key :  ; défaut=—
walter-router analyze
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
walter-router ask
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  question :  ; défaut=—
  --option :  ; défaut=—
  --context :  ; défaut=—
walter-router brief
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  --json : versioned stable note for walter-context and harnesses ; défaut=false
  --write : write it to the instance's state/router/brief.md and re-render the agent profiles (walter-soul) when it changed ; défaut=false
walter-router button
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  data :  ; défaut=—
walter-router classify
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  request :  ; défaut=—
  --context : one line on what the conversation was about before this request ; défaut=—
walter-router decide
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  task :  ; défaut=—
  intent :  ; défaut=—
  --level :  ; défaut=— ; valeurs=["L1", "L2", "L3"]
walter-router decision-bench
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  action :  ; défaut=— ; valeurs=["build", "run", "label", "serve", "status", "report"]
  --host : serve: address to listen on (the tailnet address, never a public one) ; défaut=—
  --port :  ; défaut=3090
  --models : run: comma-separated decision offers (default: the bench's list) ; défaut=—
  --samples :  ; défaut=3
walter-router decision-chain
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
walter-router declare
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
walter-router docs
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  --write : regenerate reference files; reads DB metadata only ; défaut=false
  --check : exit nonzero on stale or incomplete reference docs ; défaut=false
  --offline : check against the committed database metadata snapshot ; défaut=false
walter-router dossier
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  task :  ; défaut=—
walter-router feedback
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  model : model_id, or 'last' for the model of the last successful routed run ; défaut=—
  rating :  ; défaut=— ; valeurs=[-2, -1, 0, 1, 2]
  --task :  ; défaut=—
  --note :  ; défaut=—
walter-router generate
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  request :  ; défaut=—
  --task :  ; défaut=—
  --role :  ; défaut=—
  --image-url :  ; défaut=—
  --voice : voice (tts), e.g. Algenib ; défaut=—
  --style : delivery style (tts) ; défaut=—
  --aspect-ratio :  ; défaut=—
  --duration :  ; défaut=—
  --resolution :  ; défaut=—
  --paid-fallback : UI-only role (Flow): generate via Kie instead ; défaut=false
  --no-craft : send the request as the prompt ; défaut=false
walter-router health
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
walter-router instance-env
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
walter-router library
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  --json :  ; défaut=false
walter-router log-exec
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  entry :  ; défaut=—
walter-router migrate
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
walter-router notify-failure
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
walter-router pick
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  task :  ; défaut=—
  --level :  ; défaut=— ; valeurs=["L1", "L2", "L3"]
  --role : favourite role, e.g. action / value / budget ; défaut=—
  --require : hard constraint (unrestricted, open_weights, video_input) ; défaut=— ; valeurs=["open_weights", "unrestricted", "video_input"]
  --agent : the view an agent gets (choice, why, routes with prices) ; défaut=false
walter-router plans
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  action :  ; défaut=— ; valeurs=["list", "set", "retire"]
  sub_id :  ; défaut=—
  --vendor :  ; défaut=—
  --plan :  ; défaut=—
  --price :  ; défaut=—
  --execution :  ; défaut=—
  --route-provider :  ; défaut=—
  --models : comma-separated model ids included in the plan ; défaut=—
  --note :  ; défaut=—
  --since : start date (YYYY-MM-DD) ; défaut=—
  --until : end date of an offer (YYYY-MM-DD) ; défaut=—
  --list-price : catalogue price when the plan is a free offer ; défaut=—
  --why :  ; défaut=déclaré par le propriétaire
walter-router postes
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  poste :  ; défaut=orchestrator
walter-router prefer
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  task :  ; défaut=—
  --objective :  ; défaut=— ; valeurs=["value", "best_available"]
  --pin : favourite model as model_id[/variant], e.g. gpt-image-2-5-sunburst/max ; défaut=—
  --provider :  ; défaut=—
  --note :  ; défaut=—
  --role :  ; défaut=default
  --watch :  ; défaut=— ; valeurs=["quality", "dominance", "none"]
walter-router preflight-bench
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  action :  ; défaut=— ; valeurs=["build", "run", "readings", "serve", "status", "report"]
  --host : serve: address to listen on (the tailnet address, never a public one) ; défaut=—
  --port :  ; défaut=3092
  --models : run: comma-separated decision offers (default: the bench's four) ; défaut=—
  --samples :  ; défaut=3
  --draw : build: the authentic draw (JSON list; default real-draw.json in the state folder) ; défaut=—
walter-router probe
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  --provider : only this status key (kie, kie-codex, openrouter, arnict) ; défaut=—
  --timeout :  ; défaut=90
walter-router publish-library
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  --no-deploy :  ; défaut=false
walter-router refresh
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  --no-notify :  ; défaut=false
  --dry-run : compose the notification without sending it ; défaut=false
  --skip-collect : re-derive the latest snapshots (no network) ; défaut=false
walter-router research
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  categories : research categories (default: all) ; défaut=—
  --source : source kind instead, e.g. aa_eval, arena (repeatable) ; défaut=—
  --list : categories with what each reads ; défaut=false
  --analyse : then recompute the choices and republish the page (no message) ; défaut=false
  --no-web : plans: skip the web research agent (meters, mails, cost price only) ; défaut=false
  --no-notify : plans: record news and proposals without sending them ; défaut=false
walter-router review
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
walter-router route
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  request :  ; défaut=—
  --task :  ; défaut=—
  --level :  ; défaut=— ; valeurs=["L1", "L2", "L3"]
  --context : one line on what the conversation was about before this request ; défaut=—
  --agent : the view an agent gets (choice, why, routes with prices) ; défaut=false
  --model : a model named by the owner: exactly that one (or why it cannot run) ; défaut=—
  --provider : with --model: that provider only (openrouter, kie, codex, arnict) ; défaut=—
walter-router run
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  --dry-run : the decision only ; défaut=false
walter-router schema
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
walter-router status
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
walter-router subscriptions
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  action :  ; défaut=show ; valeurs=["show", "refresh", "calibrate"]
  sub_id : calibrate: subscription id (anthropic-pro) ; défaut=—
  percent : calibrate: weekly %% shown by the vendor ; défaut=—
walter-router sync-hermes
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  --apply : apply (config backup + graceful gateway restart) ; défaut=false
  --no-restart :  ; défaut=false
walter-router tasks
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
walter-router transcribe
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  files :  ; défaut=—
  --source : caller name recorded by walter-llm ; défaut=walter-router
walter-router verdict
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  alert_id :  ; défaut=—
  decision :  ; défaut=— ; valeurs=["adopted", "dismissed"]
  --note :  ; défaut=—
  --role : with a short number covering several roles: only this one ; défaut=—
walter-router web
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
  --message : instead of a JSON spec: just this message, default service, default model ; défaut=—
walter-router web-commands
  -h, --help : show this help message and exit ; défaut===SUPPRESS==
```
