# Exécution, résultats et limites

## Sélection et identité

Le routeur distingue le modèle canonique (`model_id`), sa variante de réflexion/rendu, l'identifiant natif de
l'offre chez un fournisseur, et l'hébergeur derrière une passerelle. Une offre ou un score ne prouve pas qu'un
exécuteur sache utiliser toutes ses capacités. `require=video_input` sélectionne des routes déclarant lire la vidéo ;
il n'attache pas automatiquement un fichier vidéo à une demande texte.

Un modèle nommé est résolu par le catalogue et les alias. Un fournisseur nommé avec lui est une restriction stricte.
Pour une sélection ordinaire, les voies d'accès du même modèle sont ordonnées par les règles du routeur. Les champs
historiques `hermes_provider` servent aux adaptateurs et aux anciens contrôles de disponibilité ; le texte natif
ne lance pas ce runtime et utilise `provider`/`model` via `walter-llm call`.

Pour une décision texte enrichie des routes, `provider` désigne toujours `execution[0].provider`, ou vaut
`null` si aucune route n’est exécutable. Cette valeur décrit la première tentative prévue ; après exécution,
`routed.provider` indique le fournisseur ayant réellement répondu. La restriction explicite reste dans `named.provider`.

## Texte natif

La boucle native fournit au modèle les consignes et le contexte, puis exécute les appels d'outils autorisés jusqu'à
une réponse finale, une limite de tours ou un budget épuisé. Chaque appel de transport vise exactement un
fournisseur/modèle, sans retry ni changement caché de modèle. Les outils déjà terminés et les messages sont
conservés lors du passage au fournisseur suivant ; la tâche ne recommence pas depuis son premier outil.

| Groupe demandé | Comportement actuel |
|---|---|
| `terminal`, `code_execution` | Outil terminal borné, Bash, droits du processus serveur |
| `file` | Lecture/écriture de texte UTF-8 sur l'hôte serveur |
| `web`, `walter-web`, `skills`, `memory` | Aucun outil natif indépendant ; les commandes Walter restent utilisables si `terminal` est aussi autorisé |
| `vision` | Refus explicite du groupe dans l'exécuteur texte courant |

Le défaut historique comprend web, walter-web, file et terminal. Une liste vide explicite désactive les outils en
CLI directe ; le port MCP courant omet les listes vides, qui redeviennent donc le défaut. Les fichiers et les
commandes utilisent un répertoire propre à l'exécution dans l'état de l'instance ; les chemins absolus et le
workdir d'un outil terminal peuvent désigner un autre emplacement autorisé. Aucune sandbox par fichier ni
confirmation imbriquée n'est ajoutée par cette boucle. Les sorties de terminal et lectures de fichier sont bornées
en taille dans le code ; ces bornes ne constituent pas une garantie de conservation intégrale.

Le budget texte commence après la sélection. Défaut effectif : 900 s, borné entre 60 et 3600 s. Les itérations ont
un défaut effectif de 40, borné entre 1 et 120. La valeur zéro signifie défaut. Une part du temps restant est
réservée aux fournisseurs suivants quand un fournisseur peut rester bloqué. Ce budget ne définit pas le temps
total d'un appel MCP, dont la sélection et les marges de transport sont distinctes. Le nombre d'itérations compte
les appels modèle, et pas seulement le nombre de commandes exécutées.

Le transport rejette les réponses vides, incomplètes et celles annonçant un autre modèle après normalisation
du préfixe et de la ponctuation. Il ne tente aucun autre modèle lorsque les fournisseurs sont épuisés. Une version
ou un alias renvoyé qui n'est pas reconnu peut donc produire un refus plutôt qu'une attribution incertaine.

## Résultat de walter_run

`schema_version=1` versionne le résultat métier de `run`. Les sous-formes dépendent du type de travail ; les erreurs
de transport/parsing peuvent être extérieures à cette enveloppe. Les consommateurs doivent accepter des champs
supplémentaires et vérifier les champs requis par le type reçu.

| Champ | Signification |
|---|---|
| `ok`, `error` | Résultat métier ; une erreur ou une réponse partielle n'est pas un succès |
| `kind` | `text` ou `media` quand le type d'exécution a été établi |
| `runtime` | `walter-router` pour la boucle texte native |
| `output` | Réponse finale texte, indépendante des avis de basculement |
| `tools` | Outils, arguments, résultats et état d'exécution observés |
| `workspace` | Répertoire serveur associé à une exécution texte réussie |
| `routed` | Modèle canonique, identifiant natif, fournisseur utilisé, réflexion, contraintes nommées et tentatives |
| `routed.attempts` | Une entrée par tentative physique : fournisseur, modèle, résultat, durée, erreur ou identifiant de réponse |
| `notices` | Liste des basculements texte : source, destination, modèle, raison et message |
| `user_notification_required`, `user_notice` | Obligation pour le caller de transmettre cet avis, y compris lors d'un échec |

Un refus précoce (paramètre non pris en charge, modèle introuvable) peut ne pas contenir les champs d'une exécution
commencée. En cas d'échec tardif, `routed.provider` peut désigner le dernier fournisseur ayant répondu auparavant ;
il ne suffit donc pas à transformer `ok=false` en succès. Examiner la liste entière des tentatives.

```json
{
  "schema_version": 1,
  "ok": true,
  "kind": "text",
  "runtime": "walter-router",
  "output": "Résultat vérifié de la sous-tâche",
  "user_notification_required": true,
  "user_notice": "Le fournisseur initial a échoué ; exécution avec le même modèle chez son fournisseur suivant.",
  "routed": {"model_id":"modèle-canonique","model":"identifiant-natif","provider":"fournisseur-effectif","attempts":[]}
}
```

Les identifiants de réponse sont renvoyés au caller. `models.exec_log` conserve les métadonnées d'exécution et les
durées, mais n'a pas de colonne d'identifiant de réponse ni de journal intégral des commandes. Les logs bruts du
harness qui appelle MCP/CLI peuvent conserver le résultat détaillé. Le rapprochement avec la facturation du fournisseur
reste une vérification distincte ; `cost_usd=NULL` signifie coût inconnu.

## Médias

La génération conserve ses transports dédiés, la préparation de prompt et, pour certains modèles, des workflows
de référence avant vidéo. La préparation de prompt et certaines recherches internes ont encore un adaptateur
runtime historique ; la suppression de ce runtime concerne le chemin texte natif, pas toutes les opérations du module.

Les résultats média comportent notamment `model_id`, `provider`, `files`, `urls`, `steps`, `errors`, parfois une
référence de tâche et un coût. Un résultat `mode=manual_ui` décrit une action à faire en interface, pas un fichier
déjà généré. Les valeurs de paramètres dépendent des schémas et valeurs par défaut du modèle ; le fournisseur
imposé reste strict. Les fournisseurs du même modèle sont essayés dans l'ordre ; un autre modèle n'est possible
que s'il a été déclaré dans la configuration média. Ce cas est signalé par `fallback_from`.

Le schéma d'avis `user_notice` est normalisé pour le texte. Le caller doit examiner les champs `errors`,
`provider` et `fallback_from` d'un résultat média et signaler un changement pertinent à l'utilisateur. Il ne doit
pas supposer que toutes les générations implémentent déjà les mêmes champs d'avis que le texte.

## Erreurs, confidentialité et annulation

- Les erreurs métier texte incluent notamment `all_providers_failed`, `budget_exhausted`, `max_turns_exhausted`,
  `unsupported_toolsets`, les refus d'entrée vision, les réponses vides, incomplètes ou de modèle incohérent.
- Une exception de fournisseur est ramenée à son type, afin de ne pas exposer la clé ou le corps de requête.
- Une classe de confidentialité n'est pas un paramètre public de `walter_run` : le harness contrôle les entrées.
- L'annulation depuis tous les transports n'est pas une garantie transactionnelle ou d'arrêt de tous les descendants.
  Une action d'outil peut déjà avoir été faite et une requête fournisseur peut déjà être facturable. Le timeout
  terminal tue son groupe de processus ; il ne restaure pas automatiquement les fichiers modifiés.
- Aucun changement automatique du modèle favori n'est autorisé par un échec d'exécution. Les propositions de
  maintenance suivent un circuit de décision distinct.

## Différences de validation entre transports

Le CLI run lit le JSON et les champs consommés par le module ; il n'effectue pas encore une validation complète
par le schéma documentaire. Les adaptateurs ont leurs propres contrôles. Le port MCP restreint notamment les
identifiants de tâche/modèle/fournisseur/contrainte/rôle/format/résolution à des mots de 1 à 64 caractères
`[A-Za-z0-9_.:/-]`, et les références image aux URLs HTTP(S). Un nom de modèle avec espaces peut être résolu
par la CLI alors que ce port le refuse. Le plugin natif valide aussi les tâches selon son inventaire chargé.

Le port MCP tronque conversation à 600 caractères pour route, mais run ne fait pas cette coupure actuellement.
Il omet les valeurs vides, nulles, zéro et false lors du transfert du spec ; tenir compte notamment des listes
d'outils vides. Le même schéma ne suffit pas à affirmer une équivalence parfaite de tous les adaptateurs.


### HeyGen Video 1

Le modèle de catalogue `heygen-video-1` dispose d’un exécuteur OpenRouter. Ses résolutions natives annoncées au 2026-10-24 sont 480p, 768p et 2K : ne pas annoncer une génération 720p native. Vérifier la présence du son sur le fichier produit, le catalogue décrivant un son synthétisé mais déclarant `generate_audio: false`.


2026-10-24 : le décodage HTTP média accepte les espaces et sauts de ligne avant un objet/tableau JSON ; les réponses binaires restent des octets.

## Route d’abonnement Claude

La route `claude-pro` est exécutée dans la passerelle du Router, avec les messages, outils et paramètres du consommateur. Le transport natif ne conserve que l’attribution technique du fournisseur ; sa boucle d’agent et son contexte ne sont pas délégués. Configuration, renouvellement, quotas réels, streaming et limites : [CLAUDE-SUBSCRIPTION.md](CLAUDE-SUBSCRIPTION.md).

## Appels HTTP des harnesses (correction du 29 octobre 2026)

La passerelle corrèle chaque requête avec son run ouvert dans Memory, sans variable de session globale.
`X-Walter-Run-Id` et `X-Walter-Task-Id` sont des UUID locaux ; le run est vérifié par la CLI publique.
DSH transmet son identifiant natif de session (`session-UUID`, ou UUID) par les options publiques pi-ai de cache ; la passerelle l’enlève avant
le transport fournisseur et cherche un run ouvert unique. Une session ambiguë ou indisponible est refusée.
Les classes `local_only` et `redacted_cloud` sont refusées pour ces contextes identifiés : cette passerelle
ne possède pas d’étape de pseudonymisation. Cette vérification ne certifie pas la confidentialité des anciens
appels dépourvus d’identité Memory.

`models.exec_log.usage` conserve les tokens d’entrée, de sortie et de cache quand ils sont retournés.
`cost_status` distingue `reported` (usage fournisseur), `estimated` (estimation positive du transport),
`legacy` (ancienne valeur sans provenance précise) et `unknown` (coût null). Un zéro synthétique du transport
reste inconnu ; un zéro explicitement retourné dans usage.cost est conservé. Les flux accumulent la dernière
mesure disponible ; une interruption avant épuisement ou un échec du nettoyage est journalisé en échec.
Une fermeture du client après épuisement peut conserver le succès fournisseur et sa raison de fermeture. Les appels sans coût
ne permettent pas de calculer un coût total complet. Installer la migration 036 avant les lecteurs et le gateway.

Le transport CLI exact retourne les mêmes mesures que le port HTTP. La boucle texte native conserve
`usage`, `cost_usd`, `cost_status` dans chaque tentative et dans le journal d’exécution, sans recalcul
concurrent des prix. Une réponse sans mesure, ou une tentative échouée sans mesure, reste inconnue.
