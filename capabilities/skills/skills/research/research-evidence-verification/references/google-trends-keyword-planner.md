# Collecter Google Trends et qualifier les lacunes Keyword Planner

(Moved unchanged from SKILL.md on 2026-11-27.)

- Pour une recherche de demande par pays, collecter séparément les fenêtres 5 ans et 12 mois, les expressions locales et une comparaison internationale utilisant la même expression. Consigner pays, termes exacts, période, catégorie, type de recherche et date de collecte. Ne jamais présenter un indice Trends comme un volume mensuel, un CPC ou une part de marché.
- Lire le contrat du projet avant toute navigation. Réutiliser uniquement la session attribuée ; sur cette VM, le navigateur se pilote avec `/opt/walter-core/bin/walter-browser -s elie-google`. Ne pas créer de compte, campagne ou moyen de paiement pour débloquer Keyword Planner.
- Préparer un répertoire de preuves et lancer une collecte séquentielle, sans multiplier les onglets :
  ```bash
  : "${PROJECT:?Définir le répertoire du projet}"
  mkdir -p "$PROJECT/evidence/trends" "$PROJECT/work/trends"
  W=/opt/walter-core/bin/walter-browser
  SESSION=elie-google
  timeout 45 "$W" -s "$SESSION" url
  timeout 60 "$W" -s "$SESSION" nav 'https://trends.google.com/trends/explore?date=today%205-y&geo=FR&q=diamant%20de%20laboratoire&hl=fr'
  sleep 5
  timeout 45 "$W" -s "$SESSION" eval 'JSON.stringify({url:location.href,title:document.title,text:document.body.innerText})' > "$PROJECT/work/trends/FR_5y.browser.txt"
  timeout 45 "$W" -s "$SESSION" shot "$PROJECT/evidence/trends/FR_5y.png"
  ```
- Remplacer `date=today%205-y` par `date=today%2012-m` pour la seconde fenêtre. Ces fenêtres sont relatives au jour réel de navigation : si la date de référence de l'étude diffère, utiliser des bornes explicites, encodées dans le paramètre `date`, et vérifier les dates effectivement affichées.
- Conserver la sortie brute du navigateur avant transformation. L'interface Explorer observée exposait les données dans `document.body.innerText` sous forme tabulée, avec un en-tête `x\ty1`. Vérifier sa présence avant de parser ; ne pas supposer ce format stable :
  ```bash
  timeout 45 "$W" -s "$SESSION" eval 'JSON.stringify({url:location.href,header:document.body.innerText.indexOf("x\ty1"),preview:document.body.innerText.slice(0,1200)})'
  ```
- Rejeter comme collecte invalide toute page d'erreur, notamment HTTP 429, toute extraction sans tableau attendu, ou tout tableau dont les dates et le nombre de colonnes ne correspondent pas à la requête. Garder les preuves d'échec avec un nom explicite, mais les exclure des agrégations. Ne pas convertir une absence de données en zéro.
- Chaque requête Trends est normalisée séparément. Ne pas classer des pays à partir des moyennes de leurs indices locaux indépendants. Pour les comparaisons géographiques, utiliser une extraction géographique commune et expliquer qu'elle reflète un intérêt relatif, non le nombre absolu de recherches. Distinguer termes de recherche et sujets, et signaler les faibles volumes ainsi que les périodes incomplètes.
- Pour Keyword Planner, tenter uniquement la consultation de l'accès existant :
  ```bash
  timeout 60 "$W" -s "$SESSION" nav 'https://ads.google.com/aw/keywordplanner/home'
  timeout 30 "$W" -s "$SESSION" eval 'JSON.stringify({url:location.href,title:document.title,text:document.body.innerText.slice(0,1500)})'
  ```
  Une navigation expirée ne prouve ni l'absence de compte Google Ads ni l'exigence de paiement. Classer ce résultat comme « accès non vérifié : incident technique ». Ne déclarer « création requise » que si l'interface le montre. Laisser volumes, CPC et concurrence vides lorsqu'ils n'ont pas été obtenus ; ne pas les remplacer par Trends ou des extraits de recherche non vérifiés.
- Après des timeouts répétés, arrêter la collecte et diagnostiquer en lecture seule :
  ```bash
  curl -sS --max-time 10 http://127.0.0.1:9377/health
  systemctl is-active camoufox-max
  systemctl status camoufox-max --no-pager | head -20
  journalctl -u camoufox-max --no-pager -n 20
  uptime
  free -m
  ```
  Un service `active` ne garantit pas que son endpoint répond. Ne pas boucler indéfiniment, créer des onglets de secours en série, supprimer des caches, tuer largement des processus ou redémarrer le navigateur partagé. Préserver la session authentifiée, enregistrer le blocage et ne reprendre qu'après rétablissement vérifié.
- Dans les transformations, séparer les champs `country`, `window` et `variant` du nom de fichier : des variantes comme `DEb` ou des noms comportant plusieurs underscores ne sont pas des codes pays. Valider les mappings avant agrégation et reconstruire les sorties après exclusion des collectes invalides.
