# Niveaux texte L1, L2, L3 : méthode et usage actuels

La méthode est implémentée dans `analysis/tiers.py`. Les constantes et leurs valeurs sont répertoriées dans
[reference/CONFIGURATION.md](reference/CONFIGURATION.md). Les modèles actuellement adoptés se consultent via
`walter-router pick general --level L1` (ou L2/L3) ; cette page ne fige aucun nom de modèle ni aucun prix.

1. Prendre chaque modèle appelable × variante de réflexion, son score AA et le coût publié de tâche corrigé
   par le rapport du prix fournisseur au prix catalogue. Conserver la provenance et l’unité des coûts.
   Quand un abonnement du propriétaire sert le modèle, son prix de revient entre aussi en compte (16/11/2026) :
   coût de tâche AA × (prix mensuel ÷ valeur API du quota mensuel de l’abonnement sur ce modèle), quota mesuré
   modèle par modèle par ModelDial (`plan/modeldial.py`). Le coût retenu est le plus bas des deux ; la route payante
   reste le secours quand le quota est épuisé.
2. Construire la frontière de Pareto stricte : par coût croissant, un point ne survit que s’il dépasse les scores
   de tous les points moins chers.
3. Calculer le gain marginal : points gagnés par dollar ajouté depuis le point précédent.
4. L1 : premier coude au-dessus de `QUALITY_FLOOR` (35 AA actuellement) ; le gain du pas suivant doit être
   au plus le gain propre divisé par `KNEE_DROP` (2 actuellement).
5. L2 : parmi les points entre L1 et la bande du plafond, maximiser les points gagnés par dollar depuis L1.
6. L3 : parmi les points dans `CEILING_BAND` (5 AA actuellement) du meilleur score, maximiser le gain par
   dollar depuis L2, ou L1 si aucun L2 n’est disponible.
   Depuis le 16/11/2026, le plafond ne compte que la frontière « abordable » : le premier point au-dessus du plancher
   qui rapporte moins de `CEILING_MIN_GAIN` (1 point AA par dollar ajouté) et tous ceux qui le suivent sont du luxe.
   Ils restent affichés sur la frontière, mais ils ne fixent plus la bande du plafond et ne sont candidats à aucun
   niveau. Avant cette règle, Fable 5.2 max (26,5 $ par tâche) écartait Opus 5.5 max de 0,5 point.
7. Règle des abonnements (propriétaire, 16/11/2026) : les abonnements sont déjà payés et ces niveaux servent tout le
   temps. L2 et L3 sont donc d’abord cherchés parmi les modèles qu’un abonnement sert, à leur prix de revient ModelDial.
   L3 = le choix de la méthode sur ces seuls modèles (Opus 5.5 xhigh plutôt que max : +1,7 point pour 66 % de quota en
   plus par tâche). L2 = le meilleur modèle d’un autre abonnement que celui de L3, moins cher par tâche que L3 (GPT-6.1
   Sol xhigh sur ChatGPT Plus pendant que L3 tourne sur Claude Pro : deux quotas au lieu d’un), à défaut le meilleur
   moins cher de l’abonnement de L3. La règle ne fait que monter un niveau : jamais sous le choix de la méthode, jamais
   au niveau de L1 ou en dessous. L1 garde la méthode, car son volume viderait n’importe quel quota. Chaque niveau ainsi
   choisi porte son « repli quand le quota est épuisé » : la même règle sur les abonnements restants (pour L3, le meilleur
   gain au-dessus du modèle de L2, pour ne jamais retomber à son niveau), sinon la méthode avec les modèles de cet
   abonnement à leur prix payant. Adopter la proposition déclare aussi ce repli (`when_quota_spent` dans les niveaux de
   l’instance). À l’exécution, quand tous les comptes de l’abonnement
   dépassent le seuil hebdomadaire (90 %) ou ont plein leur fenêtre de session, le niveau passe sur ce repli au lieu de
   payer le modèle au prix API (`quota_switch` dans la réponse). Il y revient dès qu’un compte a de nouveau du quota.

Si les points exploitables ne suffisent pas, le calcul ne fabrique pas trois niveaux artificiels. Les détails
et cas limites sont dans la fonction `compute`, sa docstring et ses tests.

Les niveaux déclarés restent applicables jusqu’à l’adoption d’une proposition. Le cycle de maintenance peut
proposer un autre niveau ; il ne modifie pas automatiquement les favoris. La fréquence effective est celle des
unités de maintenance déployées, décrite dans le README, et non une promesse de recalcul à chaque demande.

L’orchestrateur choisit le niveau pour le texte général. Une tâche spécialisée possède ses benchmarks et son
classement propres ; lui passer L3 n’est pas une méthode générique pour régler sa réflexion. Un abonnement
intervient dans l’accès et son prix de revient ; il ne rend pas tout appel intrinsèquement gratuit. Ce prix de revient
suppose le quota entièrement utilisable : il ne dit pas combien d’appels le quota hebdomadaire absorbe, ce que règle
l’exécution (abonnement d’abord, routes payantes quand le compteur approche de la limite).

À l’exécution texte, une panne entraîne l’essai du fournisseur suivant du même modèle. En dehors du repli
« quota épuisé » déclaré par le propriétaire (étape 7), aucun repli vers un autre modèle n’est activé par cette page. Une impossibilité est explicite et l’avis est transmis à l’utilisateur.
