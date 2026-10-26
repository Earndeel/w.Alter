# Exploitation et réglages

## État, diagnostic et provenance

```bash
walter-router health
walter-router status
walter-router review
walter-router alerts --all
walter-router dossier coding
walter check
walter contracts check
```

`health` contrôle l'alimentation et l'utilisabilité ; un modèle ou un fournisseur non testé reste distinct d'un
fournisseur disponible. `review` est un résumé déterministe du dernier cycle ; il peut rester historiquement
inchangé après une correction d'alias tant qu'aucun recalcul n'a eu lieu. Une absence dans `alerts` sans `--all`
ne suffit pas à conclure qu'il n'existe aucune alerte ouverte : examiner aussi kind et status.

Le cycle de maintenance recherche les sources, les analyse, relève les abonnements, propose les changements et
publie la bibliothèque. Sa fréquence est portée par les unités déployées, actuellement le cycle de 48 h décrit
dans le README. `--skip-collect` recalcule les relevés existants ; il ne les rend pas plus récents.

## Paramètres qui gouvernent les choix

| Sujet | Réglage / provenance | Sens |
|---|---|---|
| Qualité | `models.task_benchmarks`, exigences de tâches, `analysis/scoring.py` | Comparaison pondérée des scores et fiabilité de la preuve |
| Niveaux texte | `analysis/tiers.py`, déclarations de niveaux | Plancher, coude et bande de plafond ; la proposition n'adopte pas un favori |
| Favoris et rôles | Déclarations de l'instance, projetées dans `models.preferences` | Modèle/variante/fournisseur, objectif et politique de surveillance |
| Fournisseurs | `serve/execution.py` | Ordre des voies d'accès, prix et état mesuré |
| Quotas | `QUOTA_SWITCH`, relevés d'abonnements | À 90 % de quota hebdomadaire consommé, l'abonnement passe après les voies payantes |
| Surcoût Kie | `KIE_MAX_PREMIUM` | Au-delà de 1,25 fois le prix OpenRouter comparable, Kie est déplacé après cette voie |
| Fiabilité réelle | `UNRELIABLE_MIN_RUNS`, `UNRELIABLE_FAIL_RATE`, `RELIABILITY_DAYS` | Au moins 3 exécutions, taux d'échec ≥ 50 %, fenêtre de 14 jours ; calcul sur les 10 dernières |
| Contrôle fournisseur | `MIN_CREDIT_USD`, `SLOW_MS` | Crédit OpenRouter inférieur à 1 USD et probe au-delà de 30 s marquent une dégradation |
| Hébergeurs | Vues `models.usable_endpoints`, `models.best_endpoints` | Disponibilité au moins 95 % sur 24 h et précision native ; flex réservé au fond |
| Cache passerelle | `KEY_TTL`, `ROUTE_TTL` | Durées actuellement de 600 s ; un état en cache n'est pas une mesure live |

Ces symboles sont des constantes dans le code, pas tous des champs modifiables en base ou des options CLI.
Leur valeur actuelle complète est générée dans reference/CONFIGURATION.md. Une valeur stockée (latence, capacité,
sorties structurées…) n'est pas nécessairement un filtre appliqué par tous les chemins : lire les règles d'exécution.

Les abonnements ont un prix de revient estimé ou mesuré, pas une gratuité intrinsèque. Les prix d'entrée/sortie/cache
sont en USD par million de tokens, les coûts média portent leurs unités explicites, et les coûts par tâche sont
ceux de la source benchmark. Comparer à paramètres égaux ; un prix par token ne devient pas automatiquement un
coût par tâche mesuré.

## Actions et effets

Les commandes de consultation n'adoptent pas de modèle. Certaines peuvent néanmoins appeler le classificateur
ou une API de quota ; une consultation n'est pas toujours un calcul purement local. `schema`, `brief` et le contrôle
de documentation n'appellent pas de modèle ; `brief` lit les tâches/rôles en base.

`probe` fait des appels fournisseur. `run`, `generate`, `ask` et certaines classifications peuvent coûter de
l'argent. `research` utilise les accès externes des sources ; le volet abonnements peut consulter les preuves
disponibles et envoyer des propositions/notices si sa politique le prévoit. Pour inspecter sans notification,
utiliser les options explicitement prises en charge (`--no-notify`, etc.) et vérifier leur portée dans l'aide.

`prefer`, `declare`, `verdict`, `feedback`, `plans set/retire`, les alias et `migrate` sont des écritures. Les
changements de favoris, plans ou publication doivent correspondre à la demande du propriétaire. Le module écrit
ses tables à travers ses propres commandes ; ne pas corriger les sélections par SQL improvisé.

## Sauvegarde et restauration

Le contrat du module expose les chemins à sauvegarder : code/configuration livrée, configuration et état de
l'instance ; le schéma `models` appartient à PostgreSQL. Les déclarations de l'instance (dont abonnements et
connaissance) peuvent être la source des projections PG : un dump des seules tables ne remplace pas ces fichiers.
Les clés fournisseur restent dans le gestionnaire de secrets, jamais dans l'export de documentation.

Sauvegarder avant modification. Restaurer ensemble code compatible, migrations, déclarations et état nécessaires,
puis vérifier les contrats, un choix et une exécution autorisée. Les journaux ou identifiants historiques ne doivent
pas être réécrits pour faire correspondre a posteriori une ancienne tentative mal attribuée.

## Documentation et recette

```bash
walter-router docs --write
walter-router docs --check
walter-router docs --check --offline
walter-router brief --json
walter-router brief --write
```

`docs --write` lit les métadonnées PG, tâches et poids ; il ne collecte aucune source ni ne modifie les choix.
`docs --check --offline` vérifie le code contre le dernier schéma public enregistré ; il ne certifie pas l'état PG
actuel. `brief --write` publie les deux représentations de la même note et réactualise les profils par l'interface
de rendu existante lorsque la note change. Un processus client déjà lancé peut conserver ses anciennes instructions.

Tests du module : `venv/bin/python -m pytest -q`. Les tests avec PG utilisent des transactions annulées et les
fichiers d'instance sont redirigés vers des dossiers temporaires. Les essais réellement facturables restent des
recettes explicites séparées. Éviter de multiplier les probes payants pour une correction purement documentaire.

## Route d’abonnement Claude

La route `claude-pro` est exécutée dans la passerelle du Router, avec les messages, outils et paramètres du consommateur. Le transport natif ne conserve que l’attribution technique du fournisseur ; sa boucle d’agent et son contexte ne sont pas délégués. Configuration, renouvellement, quotas réels, streaming et limites : [CLAUDE-SUBSCRIPTION.md](CLAUDE-SUBSCRIPTION.md).
