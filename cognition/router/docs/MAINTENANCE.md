# Maintenir une documentation exacte

## Sources et productions

| Référence | Source de vérité | Contrôle |
|---|---|---|
| Paramètres des quatre outils | `serve/api.py`, comportements d'exécution, schémas des adaptateurs | Couverture des champs consommés par run et référence générée |
| CLI | `cli.build_parser()` | Toutes les commandes/options sont parcourues, sans les exécuter |
| Base | Catalogue PG `models`, commentaires SQL et significations dans `documentation.FIELD_MEANINGS` | Une colonne de table inconnue bloque la génération |
| Tâches/benchmarks | Registre des tâches et affectations de benchmarks PG | Référence déterministe ; aucun favori ou compte privé exporté |
| Constantes, environnement, configuration livrée | AST Python et fichiers de configuration du logiciel | Inventaire régénéré ; pas de lecture de la configuration privée |
| Note orchestrateur | `serve/brief.py` et clés de tâches/rôles | Limite de longueur, empreinte et tests du contrat d'injection |
| Inventaire du code | Modules Python, signatures et docstrings | Référence régénérée avec empreintes des sources |

Les schémas MCP d'un client connecté restent ceux que ce client expose effectivement. La référence du module ne
met pas à jour à elle seule une ancienne connexion MCP ou le code d'un adaptateur. Toute évolution d'API doit
mettre à jour et vérifier ces ports, en conservant les différences de transport documentées.

## Lors de chaque changement

1. Modifier le code et les contrats, puis les descriptions des paramètres et des données correspondantes.
2. Ajuster les guides si le comportement, les limites, les permissions ou les effets changent.
3. Appliquer les migrations autorisées avant de décrire le schéma live. Ajouter la signification d'une nouvelle
   colonne dans le commentaire PG ou dans FIELD_MEANINGS ; ne pas publier un champ sans explication.
4. Exécuter `walter-router docs --write`, puis `walter-router docs --check` sur l'installation de référence.
5. Lancer les tests pertinents ; la suite comprend un contrôle hors ligne de la documentation et des cas négatifs
   prouvant la détection de références périmées ou de paramètres non couverts.
6. Si la note change, `walter-router brief --write` met à jour sa publication d'instance. Les consommateurs
   chargent la nouvelle révision entre deux tours ; ils ne remplacent pas le préfixe au milieu d'une boucle d'outils.
7. Ajouter la décision fonctionnelle à HISTORY.md. Les documents historiques restent marqués comme tels.

Les fichiers de reference/ sont générés. Leur `catalog.json` contient le contrat public versionné, les métadonnées
de base, le registre des tâches, l'inventaire et les empreintes des sources. Il ne contient ni relevés de compte,
ni tokens, ni clés, ni prompts personnels, ni favoris privés. L'export public du schéma n'est pas un backup des données.

## Contrôle automatique et limites

`docs --check` renvoie un statut non nul et la liste des fichiers périmés. Il ne les corrige pas silencieusement.
Le contrôle hors ligne est intégré à la suite de tests ; le contrôle live ajoute la comparaison au schéma et au
registre PG courants. Les empreintes obligent à régénérer la référence après un changement de code ou de migration.

Le contrôle mécanique n'interprète pas tout le langage naturel des guides. Un changement sémantique exige toujours
une relecture humaine des exemples, des limites et de la note. Les champs JSON de fournisseurs restent extensibles ;
ce contrôle ne leur invente pas un schéma exhaustif. L'inventaire des constantes exclut les expressions calculées
et les valeurs locales : leurs comportements doivent être expliqués dans le guide concerné et le code.
