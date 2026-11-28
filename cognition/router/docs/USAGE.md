# Utiliser Walter Router

Walter Router sélectionne un modèle réellement accessible pour une tâche et sa voie d'exécution. Il rapproche
les noms de modèles, compare les benchmarks et les prix, tient compte des accès déclarés et conserve les décisions
du propriétaire. Le harness reste l'orchestrateur : il définit le travail, les données autorisées, vérifie le résultat
et le présente. Le modèle principal du harness ne change pas lorsqu'il appelle une capacité du routeur.

## Choisir le bon outil

| Outil | Usage | Entrée essentielle |
|---|---|---|
| `walter_run` | Faire une sous-tâche texte ou une génération média autorisée | `request`, spécialité ; texte : `goal` et `context` |
| `walter_route` | Examiner un choix, ses prix et ses routes | demande ou tâche ; ne réalise pas le travail |
| `walter_decide` | Choix court, classification ponctuelle, décision répétée | question, au moins deux options, contexte utile |
| `walter_plans` | Lire les abonnements ; enregistrer une déclaration demandée | action et champs déclarés, avec leur provenance |

Un appel direct à `walter_run` suffit quand la sous-tâche est claire. Faire systématiquement `route` puis `run`
double le travail de préparation et n'épingle pas le résultat de la première consultation : les deux appels sont
indépendants. Examiner les routes d'abord est utile pour auditer un prix, préparer un plan ou vérifier une contrainte.

Une sous-tâche déléguée doit justifier son coût et sa latence : spécialité utile, unité de travail autonome ou
économie mesurable. Une réponse très simple déjà disponible dans le contexte ne nécessite pas un appel supplémentaire.
Le routeur ne garantit pas qu'une délégation soit meilleure que le modèle déjà actif sur chaque petite demande.

## Donner une consigne exploitable

`request` porte la demande originale et sert à la sélection. `goal` décrit intégralement le travail texte : résultat
attendu, contraintes, vérifications, limites d'action. `context` fournit faits, extraits, chemins accessibles sur
l'hôte d'exécution et décisions déjà prises. L'exécuteur ne voit pas la conversation de l'orchestrateur.
`conversation` est une courte indication pour le classificateur, par exemple « suite d'une analyse de contrat » ;
ce n'est pas un remplacement du contexte de travail.

```json
{
  "request": "Corriger le calcul de médiane",
  "task": "coding",
  "goal": "Implémenter la correction dans le fichier indiqué. Vérifier les listes paires, impaires et vides. Rapporter les vérifications réellement effectuées.",
  "context": "Chemin absolu sur l'hôte du routeur, contenu utile du fichier, règles locales et périmètre autorisé.",
  "toolsets": ["file"],
  "max_turns": 8,
  "budget_seconds": 120
}
```

`file` ne lit et n'écrit que dans l'espace de travail privé du run (chemins relatifs). `terminal` et
`code_execution` sont refusés (`toolset_disabled`) depuis le 09/11/2026 : l'ancien terminal s'exécutait sans bac à
sable ; l'exécution de commandes reviendra par le bac à sable du moteur Walter.

Ne pas inventer les fichiers ou les faits manquants. Un chemin de l'ordinateur du harness n'existe pas nécessairement
sur la VM du routeur. Préparer les entrées à l'aide des transferts autorisés par le harness ou fournir leurs extraits.
Ne transmettre aucun secret ni contenu `local_only` à un modèle cloud ; le contrat actuel ne porte pas de champ
de classification de confidentialité qui effectuerait automatiquement cette vérification.

## Spécialités, niveaux, objectifs et contraintes

- `task` est la spécialité : code, rédaction, frontend, analyse de documents, sciences, domaines spécialisés,
  médias… La liste exacte vient de `walter-router tasks` et de [reference/TASKS.md](reference/TASKS.md).
- `level` vaut L1, L2 ou L3 pour le texte général : quotidien ; travail en plusieurs étapes ; raisonnement complexe
  ou fort enjeu. Une spécialité a son propre classement : L3 n'est pas un réglage universel de tous les modèles.
- `role` précise un objectif média, notamment vidéo. Il est distinct de la spécialité et de l'effort de réflexion.
- `require` impose une seule contrainte dure : poids ouverts, politique de contenu compatible, ou entrée vidéo.
  Une contrainte filtre la sélection ; elle ne fabrique pas un outil ou un attachement multimédia.

Quand la tâche est déjà fixée, le routeur évite la classification inutile, sauf objectifs vidéo à déterminer ;
pour `general`, fournir aussi le niveau évite de redemander ce choix au classificateur.

```json
{"request":"Comparer ces deux options","task":"general","level":"L2","goal":"Comparer coûts, compromis et incertitudes, puis motiver le choix.","context":"Les deux options et les critères de l'utilisateur."}
```

Si le propriétaire nomme un modèle, transmettre `model`, éventuellement `modèle/variante`. S'il impose aussi un
fournisseur, transmettre `provider` : cette restriction reste stricte. Un favori et un fournisseur épinglé dans
les préférences sont des notions distinctes : le classement des routes garde ses règles d'accès et de fiabilité.

## Lire les résultats et informer

Une sélection n'est pas une exécution. Lire le résultat réel : `ok`, erreurs, fournisseur et modèle effectivement
utilisés, tentatives et traces d'outils. Pour le texte, les fournisseurs suivants du même modèle sont essayés
après un échec ; l'historique et les outils terminés sont conservés. Aucun autre modèle n'est substitué automatiquement.

Quand `user_notification_required` est vrai, transmettre `user_notice` à l'utilisateur, y compris après un échec.
Ne pas présenter une tentative échouée comme réussie, ni un coût absent comme nul. Les identifiants de réponse
permettent de rapprocher les traces du fournisseur ; les métadonnées locales ne certifient pas son tableau de facturation.

## Médias et décisions courtes

Pour les médias, conserver la demande originale et fournir les paramètres utiles au média. Les valeurs admises
de durée, résolution et format dépendent du modèle. La génération peut coûter de l'argent et exige la demande
de l'utilisateur. `paid_fallback` est un consentement à employer une voie payante pour un rôle prévu en interface
manuelle ; ce n'est pas un simple réglage de disponibilité.

```json
{"question":"Faut-il approfondir cette demande ?","options":{"oui":"Une information indispensable manque","non":"Les éléments suffisent pour répondre"},"context":"Éléments réellement disponibles."}
```

Le modèle de décision convient à ce choix discret. Il ne remplace pas une analyse longue, une recherche documentée
ou le contrôle de qualité d'un livrable important.
