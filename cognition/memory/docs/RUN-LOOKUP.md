# Retrouver le run ouvert d'une session

`walter-memory runs find --session <clé>` garde son comportement historique : dernier run de cette session,
quel que soit son état, réponse `{"run_id":"…"}` ou `{"run_id":null}`. Ses consommateurs existants sont inchangés.

Pour corréler un appel de modèle au traitement en cours, utiliser explicitement :

```sh
walter-memory runs find --session dsh/vm/<session-id> --open-only
```

La sélection demande à la fois la clé de session exacte et `status = 'open'`. Aucun run clos ni run d'une
autre session n'est utilisé comme repli. Si plusieurs runs sont ouverts pour cette même session, la commande
refuse la corrélation : les trois métadonnées sont `null` et `error` vaut `ambiguous_open_runs`. Elle ne choisit
pas silencieusement le run le plus récent.

La réponse est limitée aux métadonnées nécessaires au consommateur :

```json
{"run_id":"identifiant-canonique", "status":"open", "privacy_class":"cloud_allowed"}
```

Sans run ouvert correspondant, les trois valeurs sont `null`. La requête ne sélectionne aucun `goal`, prompt,
message ou contenu personnel. La confidentialité retournée est celle du run ; le consommateur la respecte
avant toute transmission à un modèle. Le lookup ne crée, ne termine ni ne modifie un run.

Un consommateur qui possède déjà un identifiant vérifie cette identité exacte avec
`walter-memory runs find <run-id> --open-only`. Ce mode demande `run_id` exact et `status = 'open'`, avec la
même réponse limitée. Il ne remplace jamais un identifiant clos/inconnu par un autre run de la session.

La passerelle peut résoudre une clé de session reçue du runtime par cette commande publique, sans importer les
internes de Walter Memory et sans état global du « run courant ». Une clé absente/inconnue reste non corrélée.

`tests/test_runs_find.py` exécute la CLI et la sélection SQL sur SQLite en mémoire : sessions distinctes,
run clos plus récent qu'un run ouvert, confidentialité, absence de correspondance et compatibilité sans flag.
Le seul ajustement au SQL PostgreSQL est le marqueur de paramètres du pilote (`%s` → `?`). Aucun PG réel n'est
contacté ; `tests/test_runs.py`, dont la fixture écrit/nettoie PG, n'est pas exécuté pour cette validation offline.

## Attester la route effectivement utilisée

`walter-memory runs routing <run-id>` lit un objet JSON sur stdin et appelle l'écriture publique
`runs.routing()`. Seuls `applied`, `via`, `model_id`, `model`, `provider` et `observed_model` sont transmis ;
les autres clés sont ignorées, l'identifiant cible reste celui de l'argument. Une cible explicite et un objet
JSON sont obligatoires. La réponse de succès est `{"ok":true}`. Aucun objectif ni prompt ne doit être envoyé.

Le producteur n'atteste `applied:true` qu'après une exécution réussie sur la route observée. Une configuration
de départ ne prouve pas son utilisation ; les hooks peuvent déclarer séparément `applied:false` et leur état
de configuration par la bibliothèque existante. Cette commande ne remplace pas le journal d'appels du modèle.

## Clore explicitement un tour en erreur

`walter-memory runs end <run-id>` reçoit sur stdin un objet JSON avec un **statut explicite obligatoire** :
`{"status":"ended"}`, `{"status":"failed"}` ou `{"status":"cancelled"}`. Une cible absente, un statut
manquant ou un autre état sont refusés avant le writer. La commande appelle `runs.end()` ; elle ne contient
aucun SQL externe ni clôture implicite du dernier run d'une session.

Le writer ne modifie qu'un run encore ouvert et émet son unique `run.ended` dans la même transaction. Un retry
ne duplique pas l'événement et ne réétiquette pas un run déjà échoué en succès. La réponse `{"ok":true}`
accuse la requête au writer, pas la réussite du scénario ; le contrôleur conserve le résultat original et
vérifie le statut persistant. Une erreur du harness doit demander `failed`, jamais `ended` par défaut.

Le parser Logs DSH (`walter_memory.logs.parse_dsh`) conserve déjà `turn/end`, son `reason`, `interrupted` et
`usage`, mais n'appelle pas le Run Plane. Le connecteur canonique `agent_sessions.parse_dsh` n'en dérive pas
d'événement de clôture. Les hooks Stop n'arrivent pas nécessairement lors d'une erreur de requête DSH.

Le correctif minimal pour un banc ou un adaptateur qui connaît l'identifiant créé au début du tour est un
`finally` appelant ce port avec cet identifiant exact et le statut réel. Garder l'exception initiale et les
assertions métier : une fermeture réussie ne transforme pas `INVALID_REQUEST` en scénario réussi. En cas
d'échec du writer, signaler que le run reste à réconcilier, sans remplacer le diagnostic initial.

Une récupération générique à partir des Logs peut réutiliser le watcher existant et la bibliothèque Memory,
mais doit relier le `turn/end` au **même tour** (identifiant/corrélation conservée au départ). Clore le dernier
run ouvert de la session au replay est dangereux : un ancien événement terminal pourrait fermer un tour plus
récent. Tant que cette corrélation n'est pas prouvée et les raisons terminales officiellement mappées, garder
ce recovery en proposition ; aucun nouveau service ni fermeture automatique heuristique n'est ajouté ici.

`tests/test_runs_end.py` exécute la CLI, le vrai writer et le bus contre une base SQLite transactionnelle
éphémère : échec, annulation, terminaison, retry, non-réécriture d'un statut terminal et refus des entrées
invalides. Aucun PostgreSQL réel n'est utilisé par ces tests.

## Comptabilité des appels du run

`walter-memory runs show <run-id>` retourne aussi `usage` et `cost_status` dans chaque entrée de
`model_calls`, en plus des champs existants. Une dépense inconnue conserve `cost_usd: null` et
`cost_status: "unknown"` ; elle ne devient pas zéro. Les autres états de coût sont `reported`, `estimated`
et `legacy`. `usage` conserve les mesures enregistrées par le producteur.

Ce lecteur requiert la migration **036 de Walter Router** ajoutant `models.exec_log.usage` (`jsonb`)
et `models.exec_log.cost_status`. Déployer cette migration avant ce code. Le test offline
`tests/test_run_model_usage.py` vérifie la lecture de deux appels, l'un sans coût connu et l'autre avec coût
déclaré ; il n'applique aucune migration PostgreSQL.

Pour revenir en arrière, remettre d'abord les anciennes sources du lecteur et des producteurs. Les nouvelles
colonnes peuvent rester en place sans gêner l'ancien code. Ne les retirer éventuellement qu'après avoir
arrêté/remplacé tous leurs consommateurs et sauvegardé les mesures ; ce correctif ne supprime aucune colonne.
