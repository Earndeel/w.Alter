# Documents conservés comme connaissances

Le processeur `walter_memory.documents` lit les documents déclarés par l'instance et publie chaque section
comme événement canonique `document.section`, puis comme connaissance `doc_section` reliée à cet événement.
Il n'appelle aucun modèle. Les documents d'exploitation ne constituent pas des instructions pour le lecteur
mémoire : ils restent des sources datées, avec leur provenance et leur confidentialité.

## Déclaration et utilisation

La configuration est trouvée par l'interface publique
`walter instance config memory documents.toml`. Elle doit être un fichier TOML valide comportant une liste
`source`, y compris lorsqu'elle est volontairement vide.

```toml
[[source]]
name = "decisions"
path = "/chemin/du/registre.md"
split = "h2"
privacy = "cloud_allowed"

[[source]]
name = "rules"
path = "/chemin/des/regles/*.md"
split = "file"
exclude = ["INDEX.md"]
```

Chaque nom doit être unique. `split` vaut `h2` (une section par titre `##`, titres répétés numérotés) ou `file`
(un fichier, sans son front matter). La confidentialité déclarée appartient à `cloud_allowed`, `redacted_cloud`
ou `local_only`. `exclude` contient des noms de fichiers, pas une chaîne unique ni des chemins.

Commandes : `walter-memory documents sync --dry`, `walter-memory documents sync` et
`walter-memory documents list`. Le passage normal de l'index appelle `sync_if_changed()` ; son empreinte tient
compte des déclarations, des dates de modification des fichiers et de la version du processeur.

## Disponibilité et retrait volontaire

Une configuration illisible, un échec de la commande d'instance, une déclaration invalide ou un fichier déclaré
indisponible font échouer le passage. Une erreur ne devient jamais une liste de sources vide. La transaction
conserve les événements, connaissances et chunks précédents ; le checkpoint n'avance pas et aucun succès de
connecteur n'est enregistré. Le passage d'index signale l'erreur tout en poursuivant l'indexation des événements.

Pour un glob, la disparition d'un fichier déjà indexé et toujours couvert par la déclaration est une
indisponibilité. Cela évite de confondre un montage absent ou un fichier momentanément déplacé avec une décision
de supprimer sa connaissance. Un glob initialement vide peut être déclaré avant l'arrivée des fichiers.

Un retrait volontaire s'exprime en supprimant une section d'un fichier lisible, en ajoutant son fichier à
`exclude`, en retirant/modifiant sa déclaration ou en écrivant explicitement `source = []` pour tout retirer.
Le retrait conserve l'historique, rétracte l'événement précédent et cache ses chunks ; il ne purge pas les données.
Les mises à jour des documents devraient être atomiques pour éviter de publier un état intermédiaire vide.

## Occurrences, provenance et idempotence

Le contenu seul ne définit pas l'identité d'une occurrence. Avec l'ancienne clé `document|hash`, un retour
A → B → A réutilisait l'événement A déjà rétracté : la nouvelle connaissance existait mais la frontière canonique
refusait de la lire. La version 2 attribue une révision croissante par clé de section et une clé canonique
`document|sha256-complet|vN`. Les attributs de l'événement et de sa connaissance portent la même révision.

La révision est calculée depuis tout l'historique `doc_section`, y compris les lignes rétractées ; les lignes
anciennes sans révision comptent comme révision 1. Un verrou transactionnel PostgreSQL sérialise les passages.
L'événement, la connaissance et le retrait de la version précédente sont dans la même transaction. Un retry
après rollback recalcule la même révision ; un passage identique réussi ne crée aucun événement ni connaissance.

Un texte réintroduit après un retrait explicite reçoit donc une nouvelle occurrence. Un texte retrouvé après
une simple indisponibilité garde son occurrence si rien n'a changé. Une ligne active dont la preuve canonique
est manquante ou déjà rétractée est remplacée par une nouvelle occurrence lors de la synchronisation, sans
jamais annuler les anciennes rétractions. La lecture conserve la frontière commune `read_policy`.

## Confidentialité

Les détecteurs inspectent la section entière et les métadonnées textuelles avant la limite de stockage de
12 000 caractères. Un motif de secret empêche tout nouvel enregistrement de la section. Une catégorie sensible
resserre la classe à `local_only`. La classe finale respecte également la classe de la source et les politiques
de Walter Memory ; une configuration documentaire ne peut pas les desserrer.

Pour une même section et un même hash, la classe la plus stricte de l'historique et de ses événements s'impose,
y compris après réintroduction. Un resserrement à texte identique est appliqué aux événements historiques
concernés, aux connaissances et aux chunks, sans modifier leur contenu. L'event store autorise explicitement
cette exception à l'append-only. Une configuration moins restrictive ne déclassifie jamais ces données.

Un changement global de politique de confidentialité suit aussi la procédure existante de rescan des données ;
le déclencheur documentaire par fichiers/configuration ne remplace pas cette procédure.

## Déploiement et validation de la correction du 29 octobre 2026

Aucune migration SQL ni réécriture de l'historique n'est nécessaire. La nouvelle version dans l'empreinte
force une relecture au premier passage après déploiement. Une synchronisation peut réparer les lignes actives
à provenance rétractée et resserrer leur confidentialité ; elle ajoute des occurrences et des rétractions par
la bibliothèque canonique. Les sources doivent être accessibles et valides pour que ce passage réussisse.

Les régressions sont dans `tests/test_documents_sync.py`, avec de vrais fichiers temporaires et une frontière
SQL transactionnelle en mémoire. Les fonctions réelles de configuration, découpage, classification,
`record_events`, retrait et `read_policy` sont exécutées. Les tests couvrent les erreurs de configuration et de
fichier, les retraits explicites, A → B → A, les réintroductions, les retries, le rollback et le dry-run, les
secrets dans les métadonnées/après troncature, les politiques de source et le resserrement de confidentialité.
Ils n'ouvrent aucune connexion PostgreSQL et n'appellent aucun modèle.

Depuis la racine du module :

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD" walter-python -m pytest -q -p no:cacheprovider \
  tests/test_documents.py tests/test_documents_sync.py
```

Ces tests ne prouvent pas l'exécution des verrous, du trigger append-only ou du plan de requête sur un serveur
PostgreSQL réel. La validation de production doit inclure le dry-run documentaire, l'indexation puis la santé
mémoire et le superviseur, après sauvegarde ; aucune de ces écritures de production n'est réalisée par les tests.
