# ops/devboard — le tableau de développement de Walter

| | |
|---|---|
| **Rôle** | Montrer en direct où en est le développement de Walter : chantiers (cartes `W-n`), accords attendus, décisions remplacées, documents de référence, ce que font les agents en ce moment. Page tailnet à la manière de Linear. |
| **Propriétaire** | Ops (builder) ; demande et choix du propriétaire du 14/11/2026 (conception et plan : rapports de l'instance du 14/11/2026, « tableau-developpement-walter »). |
| **État** | en construction (14/11/2026). |
| **Ne fait pas** | Pas une source de vérité : DECISIONS.md, V1.md et les plans le restent, le tableau les lit. Aucune action hors des deux boutons du propriétaire (ci-dessous), et seulement depuis Walter Web ; le tableau ne fait jamais le travail lui-même et ne répond jamais à une demande d'accord à la place du propriétaire. Ne lit jamais les conversations Telegram ou web de le propriétaire, ni le mode personnel W.Alter, ni les sessions du moteur. Ne nomme aucun modèle. |
| **Contrats** | composant `devboard` de [../contracts/ops.json](../contracts/ops.json) ; schéma PostgreSQL `devboard` ([migrations/](migrations/)) ; CLI `walter-devboard` ; HTTP tailnet `:3093` (lecture) + boucle locale `actions_port` (`:3094`, celle que relaie le panneau de Walter Web : boutons) ; Engine API (`core/interfaces/api`, porte `web`) ; MCP `devboard_correct`. |

## Comment il se remplit
- **Sans modèle** : documents (VISION, DECISIONS, V1, ARCHITECTURE, RUNBOOK, `docs/` des modules, rapports), commits
  des dépôts de modules, sessions de walter-logs (`walter-memory logs digest`), état des modules (`walter status`).
- **Avec un modèle** : le poste du Router `devboard_reading` (épinglé par le propriétaire, sur abonnement) lit le condensé des sessions de technicien (Claude Code ouvert dans le dossier de technicien (`technician_cwd`), Codex) et en tire les
  chantiers ; il lit chaque nouvelle décision pour savoir laquelle elle remplace. Appel
  `exact:<modèle du pick>@claude-pro` : jamais de repli payant. Pause seulement quand tous les comptes Pro sont à leur limite réelle (compteur à 100 % ou fenêtre de 5 h pleine) ; un refus réel (429) met aussi en pause.
- **Preuves** : chaque carte cite sa source (session#seq, décision, commit, tâche). Une correction de le propriétaire
  (`devboard_correct`) l'emporte toujours.

## Les deux boutons (15/11/2026, demande du propriétaire)
Sur chaque carte, dans le panneau « Développement » de Walter Web seulement (la page tailnet `:3093` n'en montre pas :
les actions ne répondent que sur l'écoute en boucle locale, derrière la connexion de Walter Web ; en-tête
`X-Walter-Action` exigé, donc jamais depuis un autre site).
- **Abandonner** (`POST api/actions/abandon {ref, reason}`) : correction `status = abandoned` par le propriétaire, avec
  sa raison ; une reprise en cours est interrompue (`turn.cancel`). Une lecture ne peut plus rouvrir la carte.
- **Reprendre** (`POST api/actions/resume {ref, note}`, `actions.py`) :
  1. le tableau rédige la fiche de reprise : titre, état, ce que ça change, consigne tapée avec le clic, preuves datées
     (sans doublon, avec l'outil pour ouvrir chaque source), activité, corrections, décisions, fichiers, blocages, issue
     de la reprise précédente, règles d'arrêt ; et, lus par la CLI `walter-memory` (cloud-safe, sans réponse = fiche
     sans eux) : le **dernier point connu** — le message entier de l'agent d'où vient la preuve de session la plus
     récente et la demande du propriétaire juste avant, jamais ce qui suit (une longue session passe à autre chose) — et
     les **tâches durables liées** (statut, fait, suite prévue, fil) ;
  2. il ouvre (ou retrouve) la conversation du chantier dans le moteur : `web/owner/devboard-w-<n>` (porte `web` = accès
     complet du propriétaire ; même conversation à chaque reprise de la carte, visible dans Walter Web), y soumet la
     fiche (clé d'idempotence = jamais deux fois), passe la carte « en cours » et la montre active (`devboard.live`) ;
     si l'instance fixe `resume_level` (L1–L3), la conversation est ouverte avec ce niveau épinglé (`session.open`
     `level`) : chaque appel de la reprise passe par ce niveau du Router (la tâche reste celle du plan), quel que soit
     le niveau jugé par le préflight, et le budget d'étapes du tour est au moins celui de ce niveau ; vide = le niveau
     du plan à chaque message ;
  3. le suivi (`follow_once`, toutes les `follow_seconds`) lit `turn.result` ; à la fin, la reprise est rangée dans
     `devboard.resumes` (statut, compte rendu), la carte prend l'état que le moteur écrit sur sa dernière ligne
     (`ÉTAT: done | waiting_owner | in_progress | abandoned`, correction signée `walter-reprise`) — jamais sur un tour
     en erreur ou interrompu, jamais si le propriétaire a abandonné la carte entre-temps —, puis un mot part au
     propriétaire (`notify_command`, Telegram sur cette instance). Au-delà de `resume_lost_hours` sans fin : `lost`.
  Une seule reprise à la fois par carte (index unique). Le moteur s'arrête et demande pour un lot du moteur, un choix
  d'architecture, de données, de budget ou de vie privée, une suppression, tout message au nom du propriétaire.

## Commandes
`walter-devboard migrate | sync-docs`

Réglages : `/walter/ops/config/devboard.toml` (défauts neutres), surchargés par `walter instance config ops devboard.toml`.
Tests : `cd /walter/ops/devboard && walter-python -m pytest tests -q` (base jetable sur le serveur de test de Walter
Memory, 127.0.0.1:5440).
