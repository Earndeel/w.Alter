# Walter LLM

Gateway de modèles des consommateurs autorisés, compatible OpenAI sur loopback. Le Router possède les choix et
leurs routes ; Secrets fournit les accès fournisseur ; chaque consommateur détient un jeton local révocable.
Le gateway transporte les messages et outils de l'appelant. Il ne crée pas une autre boucle d'agent.

## Interfaces et dépendances

- HTTP `/v1/chat/completions`, `/v1/models` ; `/health` ne certifie aucun fournisseur.
- `walter-llm call` : une route exacte, JSON sur stdin/stdout, sans repli de modèle implicite.
- HTTP `/v1/web/converse` (2026-11-08) : services web conversationnels. Règle déterministe de la table
  `web_services` (config, relue à chaud : service → recette Browse hôte/capacité, session moteur, site de connexion,
  `enabled`) ; exécution par le client public de Browse (`walter_browse.converse`, dans ce processus, sans
  sous-processus) ; réponse rendue telle quelle avec ses métadonnées (statut, mode `replay|discovery|repair|log`,
  version de recette, conversation, `request_id`, temps `external_ms` / `walter_ms` / `router_ms`). Un service
  désactivé est refusé (403) avant toute action navigateur. Journal : `kind=web`, `provider=web:<service>`, jamais le
  message ni la réponse. Jeton d'agent `hermes` (commande Telegram `/gpt` du plugin Router). Champs facultatifs :
  `model` (absent = modèle déjà choisi dans le service, rien n'est cliqué), `files: [{name, data}]` (base64, 10 au
  plus, 50 Mo chacun, écrits dans un dossier temporaire supprimé après l'appel) ; fichiers produits rendus en base64
  dans `files` (budget 100 Mo). Le journal garde seulement `model_choice`, `files_in`, `files_out`.
- Router et Secrets requis ; Memory optionnel pour retrouver le run ouvert d'une session DSH via sa CLI publique.
- Configuration et état personnels dans l'instance ; aucune clé fournisseur dans une requête du modèle.

## Corrélation et coût

Les headers locaux `X-Walter-Run-Id` et `X-Walter-Task-Id` sont des UUID de corrélation par requête. Ils ne donnent
aucune permission et ne sont jamais transmis aux fournisseurs. Une valeur invalide est refusée sans être affichée.

DSH transmet déjà sa session native à pi-ai. Sur sa seule route locale Walter, les options publiques
`cacheRetention: long` et `compat.supportsLongCacheRetention: true` transportent cette identité dans
`prompt_cache_key`. Le gateway la consomme comme `dsh/vm/<session>` et appelle
`walter-memory runs find --session <session> --open-only`. L'identifiant de session n'est jamais traité comme un
identifiant de run. La résolution est locale à la requête ; pas de dernière session globale ni de modification
des requêtes immuables du harness. `prompt_cache_key` et `prompt_cache_retention` sont retirés avant le fournisseur :
cette convention locale ne promet aucune rétention de cache de 24 heures en amont.

Dès qu'un identifiant de run ou une session DSH est fourni, le gateway exige un run ouvert résolu par la CLI
Memory. Pour un run explicite : `walter-memory runs find <run_id> --open-only`. Une résolution absente, ambiguë,
fermée ou indisponible bloque cet appel ; les identifiants explicite/session contradictoires sont refusés. Seule
la classe `cloud_allowed` est acceptée : `local_only`, `redacted_cloud` et une classe inconnue sont refusées, car ce
gateway n'a pas d'étape de pseudonymisation. Un identifiant de tâche seul exige aussi un run résolu.

Les appels historiques sans aucun identifiant restent possibles et non attribués ; cette compatibilité ne prouve
pas leur conformité aux politiques Memory. Les headers sont de la corrélation, pas une permission. Un contrôle
du contexte identifiable ne transforme pas le gateway en moteur complet de politique des données. Le hook DSH
annonce seulement `configured:true, applied:false` ; seule une observation de transport doit établir la route
réellement appliquée.

Chaque requête possède sa corrélation propre, même quand les réponses se terminent dans un autre ordre. Le writer
Router n'utilise `WALTER_RUN_ID`/`WALTER_TASK_ID` que si la clé correspondante est absente de l'entrée. Un `null`
explicite reste inconnu et ne peut hériter du run d'un autre appel.

Le JSON de télémétrie et `models.exec_log` conservent les UUID, les tokens mesurés, le coût quand disponible et
`cost_status` : `reported` (usage fournisseur), `estimated` (calcul du transport), `legacy` (ancienne valeur sans
provenance), `unknown` (absent). Un zéro explicitement fourni dans l'usage fournisseur est conservé. Un zéro
caché dans les métadonnées LiteLLM reste inconnu : la bibliothèque peut le synthétiser sans prix disponible.
Un coût caché strictement positif est une estimation, pas une facture. En streaming, le dernier usage reçu est
conservé ; une interruption sans usage reste inconnue. Ces valeurs portent sur les tentatives enregistrées et ne
prouvent pas l'exhaustivité de la facturation. Aucun prompt ni réponse n'entre dans cette télémétrie.

Un stream ne devient réussi qu'à l'épuisement normal de son itérateur fournisseur. Annulation, fermeture anticipée
et erreur pendant le flux restent des échecs ; aucun repli fournisseur ne rejoue une réponse déjà commencée.
La fermeture est bornée à cinq secondes et la journalisation se fait aussi quand elle échoue. Les diagnostics de
la télémétrie conservent des types d'erreur, jamais les messages bruts des exceptions fournisseur.

## Abonnement d'abord, essais plafonnés (2026-10-30)

- Un abonnement qui a encore du quota (Claude Pro, Codex) passe toujours avant toute route payante, même après des
  échecs récents (`serve/execution.py`). Un refus « rate limit » d'un abonnement est attendu puis réessayé
  (`RATE_LIMIT_WAITS`, 4 puis 12 s) avant tout repli payant ; il est journalisé `skipped='rate_limit'` et ne rend pas
  l'abonnement « non fiable ».
- Les runs ouverts par `walter-scenario` (donc aussi `walter-lab`) sont du canal `test` (`WALTER_RUN_CHANNEL`).
  Leur dépense chez les fournisseurs payants (Kie, OpenRouter, Arnict) est plafonnée à `test_budget.paid_limit_eur`
  (2 €) sur 24 h glissantes ; au-delà, chaque route payante leur est refusée (`skipped='test_budget'`) et le propriétaire
  reçoit un message Telegram par fenêtre. Lui seul valide un montant de plus :
  `walter-llm test-budget approve <EUR> [note]` (valable 24 h) ; `walter-llm test-budget` = état.
  Journal : `@instance/state/llm/test-spend.jsonl` (coût fournisseur, sinon estimé depuis l'usage ou la taille).

## Maintenance et validation

Migration Router `036_exec_telemetry` avant activation des producteurs et lecteurs de ces colonnes. En cas de
retour arrière, rétablir les lecteurs/producteurs avant toute intervention sur le schéma ; conserver les colonnes
additives est compatible avec les versions précédentes. Aucun coût historique n'est recalculé silencieusement.

Tests : `tests/test_gateway_telemetry.py` du Router (HTTP/streaming factices, confidentialité, corrélation et
écriture de télémétrie, annulations, fermeture en erreur, isolation de trois requêtes simultanées et null explicite).
Les lookups des fixtures sont exécutés inline pour éviter le blocage du pool dans le sandbox ; les requêtes ASGI
et attentes des fournisseurs restent asynchrones et se chevauchent. Ces tests n'utilisent ni DB, socket réseau,
secret ou fournisseur réel. Une sonde réelle est nécessaire pour attester qu'un harness donné fournit sa session.
Redémarrer uniquement `walter-llm` après installation, puis vérifier `/health` et une requête corrélée via le banc.
Les processus DSH déjà lancés conservent leur configuration chargée ; les nouveaux lancements prennent le port.
