# Documentation Walter Router

Cette documentation décrit le contrat public, les données, les réglages et les limites du module actuellement
implémenté. La note courte destinée à l'orchestrateur est produite par le même module ; elle ne remplace pas cette
référence technique et ne contient ni catalogue de modèles choisis, ni prix, ni secrets.

## Parcours de lecture

| Besoin | Référence |
|---|---|
| Comprendre et utiliser efficacement les quatre outils | [USAGE.md](USAGE.md) |
| Brancher un harness, authentification, permissions et diagnostic | [INTEGRATION.md](INTEGRATION.md) |
| Résultats, échecs, délais, outils, médias et limites réelles | [EXECUTION.md](EXECUTION.md) |
| Exploiter, mettre à jour, sauvegarder et diagnostiquer le module | [OPERATIONS.md](OPERATIONS.md) |
| Maintenir et vérifier cette documentation | [MAINTENANCE.md](MAINTENANCE.md) |
| Note à injecter et contrat avec walter-context | [ORCHESTRATOR.md](ORCHESTRATOR.md) |
| Tous les paramètres des outils et toutes les commandes CLI | [reference/API.md](reference/API.md) |
| Toutes les tables/vues, colonnes, types, défauts, contraintes et index | [reference/DATABASE.md](reference/DATABASE.md) |
| Toutes les tâches et leurs poids de benchmarks | [reference/TASKS.md](reference/TASKS.md) |
| Constantes littérales, noms de variables d'environnement et clés de configuration livrées | [reference/CONFIGURATION.md](reference/CONFIGURATION.md) |
| Modules Python, fonctions, signatures et documentation du code | [reference/CODE.md](reference/CODE.md) |
| Référence exploitable par des outils et empreintes des sources | [reference/catalog.json](reference/catalog.json) |
| Vue générale du stockage, de sa provenance et des responsabilités | [DATA.md](DATA.md) |
| Méthode de calcul des trois niveaux texte | [TIERS.md](TIERS.md) |

Le guide [CLAUDE-SUBSCRIPTION.md](CLAUDE-SUBSCRIPTION.md) décrit la route optionnelle d’abonnement Claude et la propriété du contexte/outillage par Walter.

## Autorité et périmètre

Le comportement exécutable et les contrats publics priment. Les références générées sont contrôlées contre le
code et les métadonnées PostgreSQL ; les guides expliquent leur utilisation. `DESIGN.md` et `HISTORY.md` gardent
la conception et les décisions datées : leurs descriptions historiques ne réactivent pas des comportements retirés.

La référence couvre le contrat du module et tous les champs SQL actuellement présents. Les documents JSON bruts
de fournisseurs (`raw`, métadonnées tarifaires, preuves) ont une structure ouverte : elle ne se transforme pas en
une liste universelle de réglages utilisateur. Les lignes privées de l'instance ne sont jamais exportées ici.

Les tests de documentation détectent une modification de code, de schéma connu ou de catalogue non répercutée.
Ils ne prouvent ni la disponibilité d'un fournisseur, ni sa facturation, ni une qualité sémantique de réponse.
