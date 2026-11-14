# Niveaux texte L1, L2, L3 : méthode et usage actuels

La méthode est implémentée dans `analysis/tiers.py`. Les constantes et leurs valeurs sont répertoriées dans
[reference/CONFIGURATION.md](reference/CONFIGURATION.md). Les modèles actuellement adoptés se consultent via
`walter-router pick general --level L1` (ou L2/L3) ; cette page ne fige aucun nom de modèle ni aucun prix.

1. Prendre chaque modèle appelable × variante de réflexion, son score AA et le coût publié de tâche corrigé
   par le rapport du prix fournisseur au prix catalogue. Conserver la provenance et l’unité des coûts.
2. Construire la frontière de Pareto stricte : par coût croissant, un point ne survit que s’il dépasse les scores
   de tous les points moins chers.
3. Calculer le gain marginal : points gagnés par dollar ajouté depuis le point précédent.
4. L1 : premier coude au-dessus de `QUALITY_FLOOR` (35 AA actuellement) ; le gain du pas suivant doit être
   au plus le gain propre divisé par `KNEE_DROP` (2 actuellement).
5. L2 : parmi les points entre L1 et la bande du plafond, maximiser les points gagnés par dollar depuis L1.
6. L3 : parmi les points dans `CEILING_BAND` (5 AA actuellement) du meilleur score, maximiser le gain par
   dollar depuis L2, ou L1 si aucun L2 n’est disponible.

Si les points exploitables ne suffisent pas, le calcul ne fabrique pas trois niveaux artificiels. Les détails
et cas limites sont dans la fonction `compute`, sa docstring et ses tests.

Les niveaux déclarés restent applicables jusqu’à l’adoption d’une proposition. Le cycle de maintenance peut
proposer un autre niveau ; il ne modifie pas automatiquement les favoris. La fréquence effective est celle des
unités de maintenance déployées, décrite dans le README, et non une promesse de recalcul à chaque demande.

L’orchestrateur choisit le niveau pour le texte général. Une tâche spécialisée possède ses benchmarks et son
classement propres ; lui passer L3 n’est pas une méthode générique pour régler sa réflexion. Un abonnement
intervient dans l’accès et son prix de revient ; il ne rend pas tout appel intrinsèquement gratuit.

À l’exécution texte, une panne entraîne l’essai du fournisseur suivant du même modèle. Aucun ancien repli L3
vers un autre modèle n’est activé par cette page. Une impossibilité est explicite et l’avis est transmis à l’utilisateur.
