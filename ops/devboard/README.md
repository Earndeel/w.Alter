# ops/devboard — le tableau de développement de Walter

| | |
|---|---|
| **Rôle** | Montrer en direct où en est le développement de Walter : chantiers (cartes `W-n`), accords attendus, décisions remplacées, documents de référence, ce que font les agents en ce moment. Page tailnet à la manière de Linear. |
| **Propriétaire** | Ops (builder) ; demande et choix du propriétaire du 14/11/2026 (conception et plan : rapports de l'instance du 14/11/2026, « tableau-developpement-walter »). |
| **État** | en construction (14/11/2026). |
| **Ne fait pas** | Pas une source de vérité : DECISIONS.md, V1.md et les plans le restent, le tableau les lit. Pas d'action depuis la page (lecture seule). Ne lit jamais les conversations Telegram ou web de le propriétaire, ni le mode personnel W.Alter, ni les sessions du moteur. Ne nomme aucun modèle. |
| **Contrats** | composant `devboard` de [../contracts/ops.json](../contracts/ops.json) ; schéma PostgreSQL `devboard` ([migrations/](migrations/)) ; CLI `walter-devboard` ; HTTP tailnet `:3093` ; MCP `devboard_correct`. |

## Comment il se remplit
- **Sans modèle** : documents (VISION, DECISIONS, V1, ARCHITECTURE, RUNBOOK, `docs/` des modules, rapports), commits
  des dépôts de modules, sessions de walter-logs (`walter-memory logs digest`), état des modules (`walter status`).
- **Avec un modèle** : le poste du Router `devboard_reading` (épinglé par le propriétaire, sur abonnement) lit le condensé des sessions de technicien (Claude Code ouvert dans le dossier de technicien (`technician_cwd`), Codex) et en tire les
  chantiers ; il lit chaque nouvelle décision pour savoir laquelle elle remplace. Appel
  `exact:<modèle du pick>@claude-pro` : jamais de repli payant. Pause quand tous les comptes Pro sont à ≥ 70 %.
- **Preuves** : chaque carte cite sa source (session#seq, décision, commit, tâche). Une correction de le propriétaire
  (`devboard_correct`) l'emporte toujours.

## Commandes
`walter-devboard migrate | sync-docs`

Réglages : `/walter/ops/config/devboard.toml` (défauts neutres), surchargés par `walter instance config ops devboard.toml`.
Tests : `cd /walter/ops/devboard && walter-python -m pytest tests -q` (base jetable sur le serveur de test de Walter
Memory, 127.0.0.1:5440).
