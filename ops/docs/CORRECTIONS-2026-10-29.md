# Propreté des dépôts et surveillance — 29 octobre 2026

Le dépôt de Backup suivait trois fichiers Python compilés dans `walter_backup/__pycache__/`. Ils sont recréés par
l'interpréteur et n'apportent aucune source ou preuve de restauration utile. Ils n'étaient pas présents dans la
copie de réparation, qui excluait les caches ; leur retrait doit donc être explicitement versionné au déploiement,
avec sauvegarde préalable. `.gitignore` empêche leur ajout accidentel après retrait du suivi.

L'ancien watchdog ne regardait que les modifications suivies. Il ignorait le travail non suivi, et un dépôt propre
pouvait contenir du bytecode déjà versionné. La nouvelle inspection utilise `git status -z --untracked-files=all`
et `git ls-files -z`, sans lire de diff ni afficher le contenu des fichiers. Elle distingue modifications suivies,
travail non suivi et preuves conservées. Les caches suivis et le travail non suivi ancien produisent des warnings
G0 dans le mécanisme Guardian existant ; aucune suppression automatique et aucun nouveau service ne sont ajoutés.

La liste de conservation configurable protège les archives et rapports intentionnels contre les faux diagnostics
de saleté. Une compatibilité enregistrée n'est pas un résidu : il faut qualifier ses consommateurs avant retrait.
Les âges mtime restent un indicateur limité, exposé comme estimation. Les fichiers supprimés n'ont plus de mtime,
et un fichier touché récemment peut contenir du travail ancien.

Sur de vrais dépôts Git temporaires, cinq des six premières régressions ont échoué avant correction : cache suivi
dans un dépôt propre, travail non suivi ancien, classement séparé des preuves, âge indépendant des edits suivis et
noms contenant des retours à la ligne. Le cas de travail récent/cache ignoré était déjà correct et reste vert.
Après correction, les tests couvrent aussi un cache déjà suivi malgré `.gitignore`, les racines de conservation
configurables, les renommages et les erreurs d'inspection. Résultat : **16 tests passent**, dont les six existants.

Le contrôle n'évalue pas le contenu des fichiers, ne certifie pas l'absence de secrets et ne déduit pas le statut
des anciens chemins. Une alerte demande de qualifier et protéger le travail ; elle n'autorise pas sa suppression.
