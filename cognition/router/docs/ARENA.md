# Collecte des classements Arena

Le parseur des données Next.js reste le même. Les chemins canoniques observés sur le site public remplacent
les anciens lorsqu’ils sont établis ; les clés de classement en base restent stables. Le 29 octobre 2026,
la page publique texte a été lue et ses 419 lignes parsées avant tout changement : la panne était de transport.

Si HTTP/FlareSolverr échoue, ou ne fournit aucun classement, la source utilise le port public `walter-browser`
via PATH, sans import de Core/Browse ni chemin vers leur code. Core et Browse sont des dépendances optionnelles :
la sélection de modèles et les autres collecteurs n’en dépendent pas. Une session publique dédiée sans login
est partagée par les pages de cette collecte, puis fermée dans finally ; aucun cookie ni secret n’est exporté.
Après un échec HTTP, les autres pages de ce passage utilisent directement ce repli.

Le CLI tronque les résultats eval à 20 000 caractères : le HTML est compressé dans la page et lu par fragments
base64 de 16 000 caractères. Taille, intégrité de décompression, origine HTTPS Arena et identité du classement
sont vérifiées avant stockage. Une redirection vers le classement général ne devient jamais un classement
français ou spécialisé. Le plafond de réponse est de 64 Mio décompressés.

Délais appliqués : 90 secondes par lecture navigateur, 600 secondes cumulées de navigateur par collecte,
puis 5 secondes pour la fermeture. Ce n’est pas un plafond du temps total : le premier transport HTTP conserve
ses délais propres, ainsi que les attentes de retry. Une indisponibilité ou un budget épuisé reste une erreur
visible. La fermeture est tentée même sur erreur ; un échec de nettoyage est signalé.

Validation : fixtures publiques minimisées, erreurs/limites et identité de board ; sonde réelle sur deux
classements, puis collecte officielle. Les collectes partielles conservent leur liste d’erreurs ; une source
sans assez de classements est refusée. Lire la couverture réelle, pas seulement la date du snapshot.

`walter-router research --source arena --no-notify` collecte sans analyse ni notification. Ne pas ajouter
`--analyse` pour une simple réparation de collecte : cette option recalcule les choix et republie la page.
Le retour arrière applicatif rétablit arena.py et le contrat ; les snapshots publics restent historiques.
