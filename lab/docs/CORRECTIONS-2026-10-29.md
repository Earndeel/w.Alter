# Correction du confinement et de la documentation — 29 octobre 2026

## Défauts et cause

La préparation conservait les liens symboliques puis appelait `chmod` sur leurs chemins : un lien pouvait changer
les permissions d'un fichier hôte. L'export suivait les liens produits par le conteneur et pouvait lire hors de son
répertoire. Le test existant contrôlait uniquement les arguments Docker. README et contrat annonçaient encore
« no sandbox yet », alors que l'interface était implémentée.

## Changement

Les copies utilisent des descripteurs de répertoires et `O_NOFOLLOW`, vérifient identité/type après ouverture,
refusent liens symboliques, hardlinks multiples et fichiers spéciaux, et bornent octets/entrées/profondeur.
Les permissions ne sont appliquées qu'aux nouvelles copies, en conservant le droit d'exécution des scripts.
Les noms de credentials courants sont exclus de l'entrée. Les résultats sont validés après arrêt confirmé du
conteneur, puis exportés vers un répertoire neuf sans écrasement. Un changement de chemin entre inspection et
ouverture ne permet plus de suivre un lien. Les sorties texte sont bornées en mémoire et le log Docker désactivé.

Le protocole des rapports intermédiaires et finaux conserve scénario, règle de décision, ordre des variantes et
empreintes de définition/code. Les valeurs d'environnement ne sont plus écrites dans les checkpoints ; seuls les
noms restent présents. Les anciens rapports sont toujours lisibles, sans réécriture ni suppression historique.

## Preuves

Les 13 premières régressions ajoutées ont échoué avant correction sur des données factices, sans démon Docker :
liens en entrée/sortie, source racine liée, FIFO, hardlinks, credentials connus, export préexistant, quota absent,
perte du droit d'exécution et probe considérant un code retour non nul comme sain.
Une régression supplémentaire a démontré que des fichiers exclus contournaient le comptage d'entrées, puis a été
corrigée. Le test du protocole a démontré l'écriture d'une fausse valeur de secret dans le checkpoint avant
correction. Les vérifications suivantes ajoutent remplacement de chemin, validation sans export, timeout, arbres
ordinaires et sorties texte volumineuses. Quatre cas supplémentaires ont reproduit les probes incomplets/invalides
considérés sains ou provoquant une exception ; ils échouent maintenant proprement. Résultat final : **27 tests
passent**, dont les quatre contrôles déjà présents. Le contrat source passe également la validation déclarative.
La commande de référence est dans le README.

## Limites et déploiement

Le Docker réel n'a pas été sollicité dans cette copie de travail. Après déploiement, exécuter le probe réel et un
aller-retour source/résultat factice. Les quotas de copie ne constituent pas un quota disque pendant l'exécution ;
les détails et restrictions figurent dans le README. Une exclusion de noms ne détecte pas un secret arbitraire.
Ce correctif ne revendique pas l'isolation d'une VM ni un backend de stockage à quota. Aucun historique d'expérience
existant n'est modifié par le correctif.

## Complément : variantes des noms de credentials

Le filtre initial excluait `credentials.yaml` mais oubliait sa variante cachée `.credentials.yaml`, les fichiers
nommés `browse-search.env`/`s3.env` et le fichier de jeton CLI `auth.json`. Le filtre reconnaît désormais les mêmes
noms connus avec un point initial, `auth.json` et les suffixes `.env`, sans inspecter le contenu ni élargir la règle
aux fichiers dont le nom contient seulement un mot comme « auth ». Douze fixtures de noms ont reproduit le défaut
en RED ; un cas positif vérifie que les noms ordinaires de documentation/code restent copiés. Aucun secret réel
n'a été utilisé. Les limites du filtrage par noms et la validation de la source restent inchangées.
