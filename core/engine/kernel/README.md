# core/engine/kernel — gel du noyau du moteur

| | |
|---|---|
| **Rôle** | Fige le noyau du moteur (DSH/Cordis `@deepseek-ai/dsh`) : version exacte, verrou npm complet, empreintes de ce qui est réellement installé, installation reproductible hors ligne, vérification. |
| **Propriétaire** | walter-core (`core/engine`) ; une mise à jour du noyau passe seulement par Lab (étude, banc, puis nouveau gel). |
| **État** | **Lot E1 en cours depuis le 09/11/2026.** Gel fait et prouvé (ci-dessous) ; l'installation en service reste `/opt/dsh`, inchangée, sous `dsh-web.service`. Reste dans E1 : rendu des compositions depuis une source (aujourd'hui fichiers tenus à la main dans `/opt/dsh/home`), rattrapage documentaire, 48 h de service inchangé. |
| **Ne fait pas** | Ne contient aucun artefact compilé ni `node_modules` (gel ≠ déplacement) ; ne modifie jamais une installation existante ; n'installe pas en production (le remplacement de `/opt/dsh` est le lot E9). |
| **Contrats** | `installed.json` (manifeste) ; commande publique `walter engine kernel` (lecture seule, code de sortie 1 en cas d'écart) ; incident `engine_kernel_drift` de la vigie d'Ops. Cache hors ligne : `/services/dsh/npm-cache` (hors git, voir son README). |

## Contenu

| Fichier | Rôle |
|---|---|
| `package.json` | Une seule dépendance, à version exacte : `@deepseek-ai/dsh` `0.2.0-rc.2` (aucune plage). |
| `package-lock.json` | Verrou complet (609 paquets, chacun avec son empreinte d'intégrité du registre), identique à celui de `/opt/dsh` pour tous les paquets. |
| `installed.json` | Manifeste de l'installation de référence : une empreinte SHA-256 par paquet installé (fichiers, bit d'exécution, cibles des liens), y compris les effets des scripts d'installation ; empreintes des 6 fichiers de composition de `DSH_HOME` ; empreinte de la configuration composée par profil (`dsh --profile <p> --dump-config`, jamais affichée). |
| `verify.py` | `snapshot <installation> [--home DSH_HOME]` produit un manifeste ; `check` le compare à `installed.json`. Bibliothèque standard seulement, lecture seule. |
| `install.sh` | `install.sh <dossier-vide> [--online]` : `npm ci` depuis le cache hors ligne, retrait des paquets optionnels construits pour musl (la machine est glibc ; l'installation de référence n'en a pas), puis `verify.py check`. Refuse un dossier non vide. |

## Preuves du gel (09/11/2026)

- Installation complète depuis le cache hors ligne dans un dossier d'essai, **deux fois** : 543 paquets ajoutés,
  3 paquets musl retirés, 0 manquant, 0 en trop, 0 différent.
- `--dump-config` des profils `web` et `headless` : même empreinte à deux exécutions (configuration déterministe),
  enregistrée dans `installed.json`.
- `walter engine kernel` sur `/opt/dsh` : conforme ; `dsh-web.service` actif.
- **Retour arrière indépendant** : archive de l'installation en service (`package.json`, `package-lock.json`,
  `node_modules`) dans `@instance/backups/changes/2026-11-09-engine-E1/` avec son empreinte SHA-256 ; restaurée
  dans un dossier d'essai par `tar` seul (sans ce dossier, sans cache, sans npm) : conforme à `installed.json`.

## Utilisation

- Vérifier l'installation en service : `walter engine kernel` (options `--install`, `--home` ; par défaut
  `DSH_HOME` ou `/opt/dsh/home` et son dossier parent). La vigie d'Ops l'appelle à chaque passage.
- Après une mise à jour décidée par Lab : nouveau `package.json`, `npm install --package-lock-only`, installation
  d'essai par `install.sh`, puis `verify.py snapshot` → `installed.json`, dans un même commit.
