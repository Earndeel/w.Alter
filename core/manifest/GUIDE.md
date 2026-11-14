# walter-core — guide détaillé

## Objectif

Le harnais commun de W.Alter : il présente les modules aux agents, expose leurs capacités sous les mêmes noms
dans chaque runtime (Claude Code, Codex, DSH, Hermes par ses plugins) et installe les raccordements. Il ne
remplace ni le runtime ni ses permissions.

## Comment l'utiliser

- **Découvrir un module** : sa ligne (D1) est dans la couche « Modules W.Alter » des instructions ; sa fiche
  d'utilisation (D2) arrive avec un message quand elle est utile, ou se lit avec `module_guide(module, depth="D2")` ;
  `module_guide(module)` (D3) donne son guide détaillé ; `module_index(module, section)` liste ce qu'il contient quand
  il publie un index. Sans argument, `module_guide()` dit où vit la présentation de chaque module. D1/D2/D3 = les
  fichiers SUMMARY / MANIFEST / GUIDE du dossier `manifest/` de chaque module (aucune copie ailleurs).
- **État** : `walter_health` (services, moteur, score mémoire, routeur, disque).
- **Déclarations techniques** : `walter_modules(module)` (contrats, dépendances, limites par harness).
- **Déléguer à Walter Engine** : `walter_run(request, goal)` (session déléguée du moteur, lectures permises, rien de ce
  qui demande le propriétaire). Prévenir le propriétaire : `walter-telegram send`. Hermes est arrêté (10/11/2026).

## Présentation des modules

Chaque module se présente depuis son propre dossier `manifest/` ; son contrat (`presentation`) ne fait qu'y pointer.

| Niveau | Contenu | Fichier / source | Accès |
|---|---|---|---|
| 1 — manifeste | Ce qu'est le module, son organisation, comment s'en servir | `manifest/MANIFEST.md` (+ partie vivante `manifest_command`) | Injecté dans chaque harness branché, couche composée par walter-context |
| 2 — index | Ce que le module contient (skills par domaine, tâches du routeur…) | `presentation.index.command`, tenu à jour par le module | `module_index` |
| Guide | Composants, interfaces par runtime, confidentialité, limites | `manifest/GUIDE.md` | `module_guide` |
| 3 — élément | Un skill, un souvenir, une entrée du coffre… | Outils propres du module | `skill_read`, `memory_search`, … |

Un module qui partage le dossier d'un autre range sa présentation dessous (`walter-memory/manifest/logs/`).

## Organisation

| Partie | Rôle |
|---|---|
| `server.py`, `walter_capabilities.py` | Serveur MCP `walter` : ports minces vers les modules |
| `walter_platform/` | Contrats, registre, chemins, instance, présentation, release, raccordement des harnesses |
| `hooks/walter_hook.py` | Adaptateur de runtime : contexte mémoire par message, journalisation des sessions, bus |
| `modules/catalog.json` → `registry.json` | Catalogue des contrats et registre compilé (`walter contracts render`) |

## Interfaces

CLI `walter` : `modules`, `status`, `check`, `doctor`, `path`, `instance`, `present notes|note|catalog|manifest|index`.

## Limites

- Les instructions du serveur MCP sont fixées au démarrage du serveur : un module ajouté ou modifié apparaît à la
  session suivante.
- Un module indisponible désactive ses propres outils, pas les autres.
