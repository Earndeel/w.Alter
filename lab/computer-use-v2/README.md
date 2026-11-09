# Étude Computer Use V2 (Adaptive Universal Operator)

| | |
|---|---|
| **Rôle** | Étude de Lab : architecture cible d'un Computer Use V2 (contexte d'appareil, présence, interruption, capacités, politique L0/L1/L2 prédite, banc anti-fausse-preuve) et son prototype en observation (« shadow », lot 2.1). |
| **Propriétaire** | lab (sujet : computer). |
| **État** | `experimental`, **à l'arrêt** depuis le 2026-11-09 : le service d'observation `computer-use-v2-shadow` est retiré, aucune fonction de production n'en dépend. Code et tests conservés (95 tests). |
| **Ne fait pas** | N'agit sur aucun appareil ; ne remplace pas `walter/computer` (production). La prédiction de politique n'a jamais été appliquée. |
| **Contrats** | `adaptive_operator/` (interfaces du lot 2.0), `docs/ARCHITECTURE.md`, `docs/BENCHMARK.md`, `benchmarks/scenarios.json`. |

## Pour un agent

- Lire `README-lot21.md` puis `docs/` (SHADOW_LOT21, ARCHITECTURE, BENCHMARK, MIGRATION, REVIEW, V1_AUDIT).
- Tests : `python3 -m pytest -q -p no:cacheprovider` depuis ce dossier (bibliothèque standard seulement).
- Toute reprise passe par un banc Lab, des tests de non-régression et l'accord du propriétaire avant d'aller vers Computer.
- Les chemins de l'ancien dossier de travail et la sonde en direct (liée à des versions de Hermes disparues) ont été
  retirés ; le spool d'observation (tiré de `state.db`) a été supprimé le 2026-11-09.
