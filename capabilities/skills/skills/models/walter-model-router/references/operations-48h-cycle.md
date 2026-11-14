# walter-model-router — Analysing, verifying and reviewing a 48-hour refresh cycle, fixing names with alias-only authority, handling an AA redesign or Intelligence Index version change.

Moved verbatim from SKILL.md on 2026-11-01.

## Analyser un cycle de 48 h et corriger les noms

- Utilise `walter-router` sur le PATH. Commence par `walter-router review`, `walter-router health` et `walter-router alias-list`. Consulte `walter-router dossier <tâche>` pour approfondir une anomalie.
- Lorsqu'une mission limite les corrections aux alias, ne lance aucun refresh, recalcul, changement de routage ou édition de fichier/base. Utilise exclusivement la commande validée pour écrire les rapprochements.
- Vérifie chaque rapprochement dans une source officielle : même modèle, version, taille et variante. Une ressemblance de nom constitue seulement un candidat ; conserve les cas ambigus sans correction.
- Consulte `walter-router alias-add --help`, puis ajoute chaque correspondance avec `walter-router alias-add <id_non_noté> <id_noté> --reason '<preuve et URL>'`. Le validateur exige un identifiant source existant, une cible ayant des scores et l'absence de chaîne ou conflit.
- Confirme les écritures avec `walter-router alias-list`, puis relis `walter-router review` et `walter-router health`. Le résumé du cycle peut conserver ses candidats et compteurs après les ajouts : distingue les alias persistés du résultat d'un recalcul, et ne lance pas ce dernier sans autorisation.
- Si `walter-router alerts` renvoie `[]`, consulte aussi `walter-router alerts --all` et examine les champs `kind` et `status` avant de conclure à l'absence d'alertes ouvertes. Pour les modèles non classés, filtre `kind == "unranked"` et `status == "open"`.
- Vérifie les résultats à partir du code de sortie et du contenu retourné : une enveloppe d'outil marquée « error » peut contenir une commande réussie avec `exit_code: 0`.
- Dans le compte rendu, sépare les corrections confirmées, les anomalies restantes et les limites du résumé enregistré. N'affirme jamais qu'un rapport a été écrit sans confirmation de sa création.


## Vérifier un cycle de 48 h sans élargir les corrections

1. Lire `walter-router review`, `walter-router health`, `walter-router alias-list` et, pour les tâches concernées, `walter-router dossier <tâche>`. Consulter `docs/TIERS.md` et `config/knowledge.json` sous la racine obtenue par `walter path router` pour interpréter les niveaux calculés et déclarés.
2. Séparer les alertes créées pendant le cycle du stock historique obtenu par `walter-router alerts --all`. Ne pas présenter le nombre total d’alertes `unranked` ouvertes comme le nombre de nouveaux modèles du cycle.
3. Lire les détails de santé : un HTTP 200 accompagné de `no_available_account` indique une indisponibilité fonctionnelle. Distinguer les providers exposés séparément dans le résultat. Une source renvoyant HTTP 500 avec zéro tableau parsé ne prouve pas un changement de structure de page ; signaler l’erreur et la fraîcheur des données.
4. Vérifier chaque rapprochement avec une source officielle et les alias déjà enregistrés. Conserver les différences de version, date, modalité et variante : une ressemblance de nom ne suffit pas à établir l’identité. Si la preuve manque, laisser le candidat sans alias.
5. Pour une identité certaine absente de la liste, utiliser exclusivement `walter-router alias-add <key> <model_id> --reason '<preuve et référence officielle>'`. Vérifier ensuite avec `walter-router alias-list` et `walter-router review`. Ne modifier ni SQL, ni configuration, ni fichier d’alias directement. Un cycle sans nouvel alias est un résultat valide.
6. Si `web_extract` signale que Brave Free ne permet que la recherche, ne pas répéter la même extraction ni changer la configuration pendant cette analyse. Employer une capacité d’extraction autorisée déjà disponible ou conserver explicitement l’incertitude.
7. Pour une variation de prix, calculer `(nouveau - ancien) / ancien * 100` et préciser le sens de la variation. Exemple : 0,239 → 0,200 correspond à une baisse de 16,32 %.

## Traiter une refonte AA et un changement de version de l’Intelligence Index

1. Avant tout recalcul, exécuter `walter-router health`, `walter-router status` et `walter-router alerts --all`. Conserver les identifiants des derniers snapshots AA et du dernier run pour comparer après correction. Lire `research/benchmarks/aa.py`, `analysis/parse.py`, `analysis/changes.py` et `analysis/alerts.py` depuis `walter path router`. Sauvegarder les fichiers avant modification.
2. Distinguer rupture de collecte et changement d’échelle. Une page HTTP 200 peut ne plus contenir le tableau attendu : lors de la refonte du 28 octobre 2026, les anciennes pages modèle renvoyaient soit aucun tableau, soit seulement 77 modèles. Ne pas abaisser le seuil de couverture pour faire passer cette collecte. Inspecter les données Next.js décodées ; le nouveau tableau était nommé `initialModels`. Parser le JSON avec `json.JSONDecoder().raw_decode`, sans dépendre d’un préfixe RSC fixe, et tester aussi les espaces autour du séparateur JSON.
3. Vérifier le contrat actuel du lecteur combinant page leaderboard et scores API. Préserver l’identité modèle × variante de raisonnement, la couverture, les coûts réellement publiés et la version de l’index. Ne pas considérer les anciennes règles « pages modèle sans clé » ou « API toujours limitée aux variantes de base » comme des invariants après une refonte.
4. Conserver `index_version` dans le snapshot et `extra.index_version` dans les lignes normalisées. Traiter une transition de version comme un changement de référentiel : ne pas produire d’alertes de progression/régression à partir de différences entre versions incompatibles. Tester séparément les changements de score au sein d’une version et la transition entre versions ; conserver les anciens snapshots comme preuve.
5. Si une clé AA est nécessaire, la conserver uniquement dans Bitwarden et la lire via `walter-secret get`. Résoudre le nom d’entrée depuis la configuration d’instance `host.json`, clé `aa_api_key`. Ne pas ajouter la valeur à un `.env`, au code, aux fixtures ou aux journaux ; ne pas réutiliser aveuglément les anciens noms d’entrée mentionnés ailleurs dans cette skill.
6. Ajouter des fixtures couvrant le nouveau payload, les tableaux absents ou incomplets, les variantes et le changement de version. Depuis la racine du router, exécuter `venv/bin/python -m pytest -q tests/test_research.py tests/test_tiers.py`.
7. Après validation du lecteur et du traitement des versions, collecter uniquement AA avec `walter-router research --source aa`. Examiner le snapshot, puis recalculer avec `walter-router refresh --skip-collect --no-notify`. Cette commande persiste un nouveau run : ce n’est pas un dry-run. Comparer les niveaux L1/L2/L3, les variantes, les frontières et les alertes avec le run précédent, sur chacune des bases de prix disponibles. Séparer les recommandations recalculées des choix effectivement épinglés.
8. Exécuter `walter-router docs --write`, `walter-router docs --check`, puis `venv/bin/python -m pytest -q`. Terminer par `walter-router health` et `walter-router alerts --all`. Documenter la migration dans `docs/DATA.md` et `docs/HISTORY.md`. Signaler explicitement tout test encore en échec ; une collecte réparée ne suffit pas à valider toute la suite.

## Review a completed 48-hour cycle with alias-only authority

- When collection and calculation have already completed, inspect their results without rerunning refresh or changing routing decisions. Start with:
  ```sh
  /walter/cognition/router/bin/walter-router review
  /walter/cognition/router/bin/walter-router health
  /walter/cognition/router/bin/walter-router alias-list
  ```
- Read `/walter/cognition/router/docs/TIERS.md` and `/walter/cognition/router/config/knowledge.json` to interpret calculated versus declared tiers. Inspect a relevant task with `/walter/cognition/router/bin/walter-router dossier <task>`; examples are `general` and `image_to_video`.
- Treat successful cycle execution and source health separately. Check individual source errors and snapshot ages even when the run status is `ok`. Report failed or stale sources as limits on the analysis; do not repair collectors under alias-only authorization.
- Use `alias-list` as the operational check for existing mappings. If a supplied alias-file path fails, do not create or edit a replacement. This session encountered a failed read of the advertised `/walter/cognition/router/walter_router/aliases.json` path.
- Verify each proposed name match using targeted evidence, preferably official model or provider documentation. Similar names, an omitted instruction-tuning suffix, or a speed-oriented variant name do not alone establish identity. Preserve distinctions between checkpoints, releases, and variants unless evidence explicitly establishes that the names refer to the same model. Do not treat an alias accepted by the CLI as proof of semantic correctness.
- Inspect the supported mutation syntax before adding a verified match:
  ```sh
  /walter/cognition/router/bin/walter-router alias-add --help
  /walter/cognition/router/bin/walter-router alias-add <source-name> <canonical-model-id> --reason "<identity evidence and source URL>"
  /walter/cognition/router/bin/walter-router alias-list
  ```
  Confirm the resulting mapping in the final listing. In this session the tool wrapper labeled successful additions as errors despite process exit code `0` and JSON containing `added` and `model_id`; inspect the payload and verify persisted state before retrying.
- Keep all writes within the user's stated scope. If only `alias-add` is authorized, do not edit the database, configuration, project files, or create a report file without separate authorization. Return findings in the response, including verified additions, unresolved candidates, and source-health limitations.
