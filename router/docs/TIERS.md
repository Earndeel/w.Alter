# Les 3 niveaux texte — la méthode de Monsieur (2026-10-02)

Monsieur ne veut pas « le meilleur modèle » pour le texte courant, mais trois niveaux fonctionnels, chacun au
meilleur rapport intelligence / prix. La méthode (code : `walter_router/tiers.py`, recalculée chaque nuit) :

1. **Données** : chaque modèle appelable × chaque niveau de raisonnement (low … max), avec son score
   AA Intelligence Index et son **coût réel par tâche** (coût AA au prix catalogue × ratio du provider le moins
   cher). L'abonnement Codex ne change pas le classement : il rend juste l'exécution gratuite.
2. **Frontière de Pareto stricte** : triés par coût, on ne garde un point que s'il fait mieux que tous les points
   moins chers.
3. **Gain marginal** de chaque point = points AA gagnés par dollar supplémentaire depuis le point précédent.
4. **L1 — économique** : premier point de la frontière au-dessus du plancher de qualité (35 AA) qui est un
   **coude** : le pas suivant rapporte au moins deux fois moins de points par dollar.
5. **L2 — intermédiaire** : entre L1 et le haut de gamme, le point qui rapporte **le plus de points par dollar
   ajouté depuis L1**.
6. **L3 — haut de gamme** : parmi les points à moins de 5 points du meilleur score (la bande du plafond), celui
   qui rapporte **le plus de points par dollar ajouté depuis L2** — le moyen le moins cher d'atteindre le haut.

Résultat du 2026-10-02 (identique au choix de Monsieur) :

| Niveau | Modèle | AA | $/tâche | Pourquoi |
|---|---|---|---|---|
| L1 | GPT-6 Luna max | 38,1 | 0,020 | coude : 467 pts/$ puis 209 |
| L2 | GPT-6.1 Sol medium | 47,8 | 0,064 | 220 pts/$ depuis L1 (high : 159, xhigh : 132) |
| L3 | Claude Opus 5.5 high | 53,6 | 0,73 | 8,7 pts/$ depuis L2 (xhigh 6,2, max 4,2) |

Repli déclaré de L3 : GPT-6 Astra xhigh via Codex (point juste en dessous sur la frontière).

**Règles** : les niveaux en vigueur sont ceux déclarés (`config/knowledge.json` → `levels`). Si le calcul de nuit
désigne un autre modèle/niveau, une seule alerte `tier` part sur Telegram ; Monsieur teste puis « adopter N »
(le niveau est alors épinglé) ou « ignorer N ». Jamais de bascule automatique. Le niveau d'une demande (L1/L2/L3)
est choisi par Jev. Pour les tâches spécialisées (code, front, 3D, vision, document…), seul le n°1 du score
pondéré multi-benchmarks est retenu.
