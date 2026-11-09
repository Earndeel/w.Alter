# core/engine — le runtime agentique unique de Walter

| | |
|---|---|
| **Rôle** | Le seul moteur agentique de production de Walter : sessions persistantes, boucle d'agent, appels d'outils, sous-agents, interruptions, permissions appliquées, événements, reprise après incident. |
| **Propriétaire** | walter-core (`/walter/core`, composante « core » de la vision). |
| **État** | **Conception** (09/11/2026). Rien ne tourne encore depuis ce dossier, aucune boucle de production n'est remplacée. Le moteur en service est DSH 0.2.0-rc.2 installé tel quel dans `/opt/dsh` (`dsh-web.service`, interface :3080). |
| **Ne fait pas** | Choisir un modèle (Router), composer le contexte (Context), se souvenir (Memory), définir l'identité (Soul), décider l'intention d'un message (preflight de Context). Il les appelle par leurs interfaces déclarées et ne refait aucune de leurs décisions. |
| **Contrats** | Brouillons dans [docs/02-ARCHITECTURE.md § 4](docs/02-ARCHITECTURE.md#4-contrats). Réutilisés tels quels : ContextPlan v2 et ChildContextSpec v1 (Context), passerelle de modèles OpenAI-compatible (Router), outils MCP walter (core), Run Plane (`runs.*`), bus Walter, vocabulaire walter_logs. |
| **Référence** | `/walter/docs/VISION.md` (§ 4 Core, § 8 flux, § 9 principes) ; décisions : `DECISIONS.md` 2026-11-09. |

## Pour un agent qui arrive ici

1. Lire [docs/01-AUDIT.md](docs/01-AUDIT.md) : les deux boucles actuelles (DSH, `walter_run`), ce que Hermes fait
   encore en production, ce qui est gardé, adapté ou supprimé.
2. Lire [docs/02-ARCHITECTURE.md](docs/02-ARCHITECTURE.md) : l'organisation interne du moteur, ses points
   d'extension (stratégies interchangeables), ses contrats et son branchement aux autres modules.
3. Lire [docs/03-MIGRATION.md](docs/03-MIGRATION.md) : les lots E0 → E9, leurs tests, leurs critères d'adoption et
   leur retour arrière. **Aucun lot n'est lancé sans l'accord de Monsieur.**

## Règles qui s'appliquent à ce dossier

- **Un seul runtime** (vision § 9). On ne construit pas de troisième boucle : le moteur est la base DSH/Cordis figée,
  adaptée par des greffons Walter. La boucle des sous-agents de `walter_run` est absorbée, pas copiée.
- **Le code amont n'est pas modifié.** Les adaptations passent par les points d'extension publics de Cordis/DSH
  (greffons, remplacement par identifiant). Un manque de point d'extension est consigné, mesuré par Lab, puis
  seulement corrigé.
- **Une seule source de vérité.** Pas de second journal, registre, bus ou mémoire : le moteur écrit dans les
  mécanismes existants (Run Plane, walter_logs, bus, `core.events` par Memory).
- **Documentation auto-descriptive** (règle de Monsieur du 09/11) : chaque sous-dossier créé ici porte un README avec
  le même en-tête (Rôle, Propriétaire, État, Ne fait pas, Contrats), déclaré dans le registre des modules.

## Arborescence prévue (rien n'existe encore hors `docs/`)

```
core/engine/
├── README.md            ce fichier
├── docs/                audit, architecture, plan de migration
├── kernel/              base DSH/Cordis figée : versions exactes, empreintes, cache hors ligne (lot E1)
├── plugins/             greffons Walter, un par point d'extension (lots E2–E5)
├── compositions/        une composition par usage (web, api, headless, essai Lab) générée par walter-core
├── contracts/           schémas JSON des contrats du moteur (lot E0)
└── tests/               tests de contrat, de reprise et de non-régression
```
