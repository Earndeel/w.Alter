# Intégrer un harness

## Consommer un Walter installé ou installer Walter

Un harness peut consommer un routeur déjà provisionné par une interface publique. Il n'a pas à importer les
dossiers Python du routeur, accéder à ses tables ou recevoir ses clés de fournisseur. Installer le service sur
une nouvelle machine implique en plus les dépendances décrites ci-dessous ; aucune installation autonome avec
un simple `pip install walter-router` n'est actuellement qualifiée.

| Porte | Contrat | Périmètre |
|---|---|---|
| MCP Walter | Quatre outils, schémas découverts par le protocole | Harnais local ou transport distant provisionné |
| CLI `walter-router` | Arguments ou JSON stdin ; résultat stdout | Processus ayant accès à l'installation Walter |
| HTTP de walter-llm | `/v1/chat/completions`, compatible OpenAI, jeton local par consommateur | Appels modèle texte ; ce n'est pas l'API des quatre outils |

Le transport local est le chemin de référence. Une connexion distante doit être provisionnée avec son
authentification, ses autorisations et ses délais. Les pages de la bibliothèque et du déclencheur de cycle ne
sont pas une API publique d'exécution. Le serveur MCP sait aussi servir HTTP en loopback ; son exposition et
son contrôle d'accès restent une opération d'infrastructure séparée.

## Raccordement MCP

Les adaptateurs connus sont Codex, Claude Code, DSH et le port natif Hermes. Sur un Walter installé :

```bash
walter harness attach codex
walter harness attach codex --apply
walter harness check codex
```

La première commande prépare un aperçu ; la deuxième sauvegarde et écrit la configuration ; la troisième vérifie
le branchement. Utiliser l'identifiant du harness concerné. Le raccordement n'installe ni un nouveau moteur
d'agent, ni un fournisseur principal, ni un moteur de contexte. Les clients déjà connectés doivent renouveler
leur connexion pour découvrir de nouveaux outils ou de nouvelles instructions.

Pour un harness non pris en charge, configurer un serveur MCP standard avec le lanceur et les arguments exposés
par l'installation Walter. Faire un handshake, découvrir les outils et leurs schémas, puis vérifier les quatre noms
`walter_route`, `walter_run`, `walter_decide`, `walter_plans`. Les schémas publiés par la connexion réelle priment
sur une copie ancienne. `walter-router schema` fournit la référence versionnée du module ; les adaptateurs ont
quelques différences de validation détaillées dans EXECUTION.md et reference/API.md.

Avec un transport SSH stdio, le lanceur doit conserver stdout pour MCP et envoyer les diagnostics sur stderr.
Ne pas mettre de mot de passe ou de clé de fournisseur dans la configuration visible du harness. Les quatre
outils ne nécessitent pas de modifier le modèle principal du client.

## CLI et API de modèles

```bash
walter-router schema
walter-router tasks
walter-router pick coding --agent
walter-router run --dry-run < demande.json
walter-router run < demande.json
```

Le résultat métier peut porter `ok=false` alors que la commande a produit du JSON avec un code de sortie nul.
Vérifier les deux. Les erreurs de parsing, d'installation ou de connexion à PostgreSQL peuvent arriver sur stderr
avec un code non nul ; le port MCP peut les convertir en une erreur générique de module.

Un client OpenAI-compatible s'adresse à la base loopback `http://127.0.0.1:8894/v1` avec son jeton consommateur.
Le champ `model` désigne alors une tâche (`coding`, `general/L2`, etc.), pas nécessairement un identifiant de modèle.
Il fournit ses propres `messages` et, si besoin, ses outils. Cette interface ne lance pas à elle seule la boucle
d'outils native de `walter_run`. Le fournisseur effectif figure dans `X-Walter-Route` et dans les journaux de passerelle.
Le consommateur provisionne son jeton via `walter-llm add-agent NAME env:FICHIER:VARIABLE` ; ne jamais l'afficher.

## Contrat d'autorisation et de contexte

Le harness autorise l'appel de capacité ; `walter_run` peut ensuite exécuter plusieurs appels modèle et outils sur
l'hôte Walter. L'exécuteur texte actuel utilise les droits de son processus, avec ses groupes d'outils et son budget.
Il n'hérite pas automatiquement du sandbox, des racines de fichiers ou des confirmations outil par outil du
harness distant. Un intégrateur doit qualifier ce point avant d'exposer l'exécution dans un environnement plus restreint.
Un simple appel de routage ne nécessite pas d'autoriser le terminal.

Les règles de confidentialité et le périmètre d'action doivent accompagner la sous-tâche. Les sources externes sont
des données, pas des instructions. Les clés fournisseur restent dans la passerelle, mais les messages fournis au
modèle peuvent contenir les données que le harness lui transmet : cette frontière doit être contrôlée en amont.

Charger la note courte de `walter-router brief --json` seulement si les outils nécessaires sont effectivement
disponibles. La placer dans la couche stable des capacités, une fois, puis conserver les mêmes octets pendant
le tour. Le contrat détaillé et le consommateur walter-context sont dans ORCHESTRATOR.md.

## Prérequis côté serveur

- Commandes `walter`, `walter-router`, `walter-llm` provisionnées sur le PATH et instance active résolue par `walter instance`.
- Environnements Python du module et de la passerelle ; transport natif terminal fondé sur Bash/processus POSIX.
- PostgreSQL et schéma `models` migré ; DSN par `WALTER_ROUTER_DATABASE_URL` ou défaut local, secret via `.pgpass`.
- Walter Secrets et les accès fournisseur nécessaires ; un fournisseur absent doit être rapporté comme indisponible.
- Pour HTTP : service walter-llm et jeton consommateur. Le transport CLI exact peut être utilisé sans démarrer un autre service.
- Pour recherche/médias/publication : dépendances et accès propres à ces capacités ; ils ne sont pas requis pour chaque simple consultation.

L'installation W.Alter dispose de contrats, d'un inventaire et d'outils d'export/restauration (`walter export`,
`walter install`, `walter release`). Consulter leur aide et vérifier un export sur une machine isolée. Les tests
sur la VM existante ne certifient pas une restauration sur un OS ou un harness non qualifié.

## Recette de branchement

1. Vérifier le handshake MCP ou la CLI et lire les schémas réels.
2. Vérifier une sélection explicite, sans appel de génération : `pick coding --agent`.
3. Préparer un travail texte minimal avec contexte autonome ; inspecter le dry-run.
4. Si les appels modèle sont autorisés, vérifier une réponse et un outil, puis rapprocher modèle et fournisseur réels.
5. Vérifier que le harness relaie `user_notice`, traite `ok=false`, conserve ses limites d'autorisation et sait récupérer les fichiers renvoyés.
6. Tester un échec simulé et l'épuisement des fournisseurs ; ne pas provoquer une panne réelle pour cette recette.

## Route d’abonnement Claude

La route `claude-pro` est exécutée dans la passerelle du Router, avec les messages, outils et paramètres du consommateur. Le transport natif ne conserve que l’attribution technique du fournisseur ; sa boucle d’agent et son contexte ne sont pas délégués. Configuration, renouvellement, quotas réels, streaming et limites : [CLAUDE-SUBSCRIPTION.md](CLAUDE-SUBSCRIPTION.md).
