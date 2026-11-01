# walter-skills — guide détaillé

## Objectif

Conserver les procédures et workflows de W.Alter indépendamment des agents qui les utilisent. Permettre au modèle de trouver la bonne capacité, de charger seulement la procédure nécessaire et de l'exécuter avec ses moyens et permissions habituels.

Le critère de réussite est une tâche correctement accomplie avec un contexte maîtrisé. Le nombre de skills, d'archivages ou de passages du Curator n'est pas une mesure de réussite.

## Découverte progressive

1. **Repère de session** : objectif de la bibliothèque, outils de navigation et liste compacte des domaines. Aucun corps de skill et aucune liste de candidats par message en mode `on_demand`.
2. **Index à la demande** : choisir un domaine pour consulter les noms, types, usages et composants des workflows. Les pages sont bornées à 20 entrées ; `next_offset` donne la suite. Les workflows précèdent les procédures individuelles. L'index ne contient que les entrées actives.
3. **Recherche par intention** : si le domaine est inconnu, décrire le besoin en français ou en anglais ; le moteur local retrouve des candidats ciblés.
4. **Lecture et exécution** : ouvrir le `SKILL.md` choisi, puis seulement les références ou scripts nécessaires. Un workflow orchestre d'autres skills ; consulter leurs procédures selon les étapes utiles.

Le modèle choisit la procédure à lire. Le Curator entretient la bibliothèque en arrière-plan ; il ne décide pas à chaque demande utilisateur. Après une erreur, la politique peut encore proposer au plus deux fiches décrivant le symptôme.

## Composants et responsabilités

| Composant | Responsabilité |
|---|---|
| `store.py` ; `skills/`, `archive/`, `drafts/` | Contenu versionné dans Git ; procédures publiées, archives et propositions |
| `registry.py` ; schéma `skills.*` | Fiches, catalogue, labels, modèles de classement, état et traces |
| `domains.py` | Publication de l'index à partir des métadonnées actives ; vue générale et navigation par domaine |
| `cards.py` | Fiches de découverte ; pas de chargement des procédures complètes dans le prompt |
| `ranker.py`, `retrieval.py` | Recherche locale lexicale et sémantique, classement, lecture des skills |
| `policy.py` | Politique commune d'exposition, indépendante des runtimes |
| `door.py`, `hermes_sync.py` | Propositions et synchronisation ; les conflits ne doivent pas écraser une modification locale |
| `curation/` | Entretien des noms, descriptions, domaines, liens et workflows ; publication de l'index après les opérations actives |
| `learning.py`, `evaluate.py` | Labels, entraînement et évaluation ; ne remplacent pas une vérification de réussite de tâche |
| `jobs.py`, `consumer.py` | Passage nocturne, réactions aux événements et réconciliation ; actualisation de l'index |
| `api.py`, `client.py` | Interfaces communes HTTP et client léger ; les adaptateurs MCP et Hermes transportent ces mêmes opérations |
| `postes.py` | Accès aux postes IA via Walter Router pour l'entretien hors du chemin de chaque message |

## Index et fraîcheur

Le contenu Git fait autorité. L'index est une projection reconstruisible publiée dans `.cache/library-index.json` et dans l'état `domain_map` du registre. Chaque entrée indique `name`, `kind`, `purpose`, `requires` ; la vue générale donne les domaines et les nombres de skills et workflows.

Le Curator republie l'index après ses opérations actives. Une simulation sur une branche ne publie pas son résultat dans l'index actif. Les événements de modification et la réconciliation republient aussi l'index après mise à jour du catalogue. Le passage nocturne le reconstruit en fin de chaîne. Une publication remplace le fichier atomiquement.

Le Curator entretient la qualité sémantique des descriptions et du classement par domaine ; la génération déterministe maintient la correspondance avec le contenu publié. Une description incorrecte doit être corrigée par la porte de proposition, pas par une modification de la projection.

## Interfaces

| Besoin | MCP commun | Hermes | HTTP / CLI |
|---|---|---|---|
| Comprendre le module | `skills_manifest()` | `walter_skills_manifest()` | `GET /v1/manifest` ; `walter-skills manifest` |
| Parcourir l'index | `skills_index(domain, offset, limit)` | `walter_skills_index(domain, offset, limit)` | `GET /v1/index` ; `walter-skills index [--domain …]` |
| Chercher par intention | `skills_search(query, context)` | `walter_skill_search(query, context)` | `POST /v1/search` ; `walter-skills search` |
| Charger une procédure | `skill_read(name, file_path)` | `walter_skill_read(name, file_path)` | `GET /v1/skill/{name}` ; `walter-skills read` |

`contracts/skills.json` décrit le contrat technique, les dépendances, les ressources et la restauration. `README.md` décrit l'exploitation. Le présent manifeste explique la structure ; il ne reproduit pas l'index vivant.

## Limites et exploitation

- Le mode `policy.discovery = "on_demand"` évite les listes de candidats par message ; `shortlist` conserve le comportement précédent pour comparaison ou retour arrière.
- Les adaptateurs doivent exposer les outils de navigation et transporter le repère de session. Un schéma d'outil déjà chargé peut nécessiter une reconnexion du client.
- Le repère compact reste susceptible de figurer dans l'historique et dans le contexte mis en cache ; aucune promesse de zéro token n'est faite.
- En cas d'indisponibilité du service, le client peut lire le manifeste local ; recherche et lecture disposent d'un repli Git. L'index indisponible est signalé explicitement.
- Les archivages, les réécritures et la pertinence des procédures demandent des validations de qualité ; la publication d'un index ne les prouve pas.
