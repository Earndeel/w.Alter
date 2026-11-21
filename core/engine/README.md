# core/engine — le runtime agentique unique de Walter

| | |
|---|---|
| **Rôle** | Le seul moteur agentique de production de Walter : sessions persistantes, boucle d'agent, appels d'outils, sous-agents, interruptions, permissions appliquées, événements, reprise après incident. |
| **Propriétaire** | walter-core (`/walter/core`, composante « core » de la vision). |
| **État** | **En service, natif depuis le 17/11/2026 16:21 UTC** : `walter_engine/` (Python, ≈ 5 400 lignes) possède tout le runtime — boucle, sessions et journal, outils, noyau Python persistant (droits du moteur), sous-agents, tâches de fond, réveils, reprise après redémarrage ou crash, Engine API v1 (:8895), porte web (:3080) — unité `walter-engine.service`, état `@instance/state/core/engine/native`. DSH (`/opt/dsh`, `dsh-web`) est **arrêté et masqué**, gardé pour le retour arrière ; ses 199 conversations ont été reprises (`walter-python -m walter_engine import-dsh`). Parité, preuves avec DSH arrêté, chemin critique : [docs/08-NATIF.md](docs/08-NATIF.md). Historique : moteur DSH composé par greffons du 10/11 au 17/11 (lots E1–E9, `/walter/docs/V1.md`, socle du 12/11 `/walter/docs/SOCLE.md`). |
| **Ne fait pas** | Choisir un modèle (Router), composer le contexte (Context), se souvenir (Memory), définir l'identité (Soul), décider l'intention d'un message (preflight de Context). Il les appelle par leurs interfaces déclarées et ne refait aucune de leurs décisions. |
| **Contrats** | Schémas brouillons dans [contracts/](contracts/), expliqués dans [docs/02-ARCHITECTURE.md § 4](docs/02-ARCHITECTURE.md#4-contrats). Réutilisés tels quels : ContextPlan v2 et ChildContextSpec v1 (Context), passerelle de modèles OpenAI-compatible (Router), outils MCP walter (core), Run Plane (`runs.*`), bus Walter, vocabulaire walter_logs. |
| **Référence** | `/walter/docs/VISION.md` (§ 4 Core, § 8 flux, § 9 principes) ; décisions : `DECISIONS.md` 2026-11-09. |

## Pour un agent qui arrive ici

1. Lire [docs/01-AUDIT.md](docs/01-AUDIT.md) : les deux boucles actuelles (DSH, `walter_run`), ce que Hermes fait
   encore en production, ce qui est gardé, adapté ou supprimé.
2. Lire [docs/02-ARCHITECTURE.md](docs/02-ARCHITECTURE.md) : l'organisation interne du moteur, ses points
   d'extension (stratégies interchangeables), ses contrats et son branchement aux autres modules.
3. Lire [docs/03-MIGRATION.md](docs/03-MIGRATION.md) : les lots E0 → E9, leurs tests, leurs critères d'adoption et
   leur retour arrière, les garanties de sécurité, les prérequis avant E1. **Chaque lot est autorisé séparément par
   Monsieur.**
4. Lire [docs/04-BASELINE.md](docs/04-BASELINE.md) (mesures de référence) et
   [docs/05-CARTOGRAPHIE.md](docs/05-CARTOGRAPHIE.md) (arborescence actuelle → cible).
5. Lire [docs/07-CONVERGENCE.md](docs/07-CONVERGENCE.md) (16/11) : noyau Python persistant en bulle, tours de
   réveil, Walter Decision — scénarios, mesures avant/après, ce qui reste.
6. Lire [docs/08-NATIF.md](docs/08-NATIF.md) (17/11) : le moteur natif, matrice de parité avec DSH, validation avec
   DSH arrêté, chemin critique d'un tour, retour arrière.
7. Règle documentaire commune : `/walter/docs/DOCUMENTATION.md`.

## Règles qui s'appliquent à ce dossier

- **Un seul runtime** (vision § 9) : `walter_engine/`, natif depuis le 17/11. On ne construit pas de seconde boucle ;
  la délégation de `walter_run` passe par l'Engine API (`delegate`). Le moteur ne réimplémente aucun module : runs,
  bus et divulgation chez Memory, plan et fenêtre chez Context, modèles chez le Router, politique dans `core/security`.
- **DSH/Cordis n'est plus une dépendance d'exécution** : `kernel/`, `plugins/*.mjs` et `/opt/dsh` ne servent qu'au
  retour arrière (et `import-dsh`, une fois). Le moteur tourne avec `InaccessiblePaths=/opt/dsh` : une dépendance
  cachée échouerait au lieu de passer inaperçue.
- **Une seule source de vérité.** Pas de second journal, registre, bus ou mémoire : le moteur écrit dans les
  mécanismes existants (Run Plane, walter_logs, bus, `core.events` par Memory).
- **Documentation auto-descriptive** (règle de Monsieur du 09/11, `/walter/docs/DOCUMENTATION.md`) : chaque
  sous-dossier significatif créé ici porte un README avec le même en-tête (Rôle, Propriétaire, État, Ne fait pas,
  Contrats) et est déclaré comme composant dans `contracts/core.json`.
- **Gel ≠ déplacement** : `kernel/` contient le verrou, les empreintes et le script d'installation du noyau, pas
  ses artefacts compilés, qui restent dans `/opt/dsh` (lot E1) ; le cache hors ligne est dans `/services/dsh`.

## Arborescence (existe : `docs/`, `contracts/`, `kernel/`, `tests/` ; le reste est prévu)

```
core/engine/
├── README.md            ce fichier
├── docs/                audit, architecture, plan E0–E9, mesures, cartographie
├── kernel/              gel du noyau DSH/Cordis : version exacte, verrou, empreintes, installation (lot E1)
├── plugins/             greffons Walter, un par point d'extension (lots E2–E5)
├── compositions/        une composition par usage (web, api, headless, essai Lab) générée par walter-core
├── contracts/           schémas JSON des contrats du moteur (lot E0, brouillons)
└── tests/               tests des contrats (E0), puis de reprise et de non-régression
```
