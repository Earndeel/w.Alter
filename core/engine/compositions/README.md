# core/engine/compositions — source des compositions du moteur

| | |
|---|---|
| **Rôle** | Source des parties de la composition DSH qui n'étaient pas encore rendues : la « face » du profil web (nom, phrase d'accueil, durée de connexion du navigateur). Rendue par walter-core (`walter harness install dsh`) dans un bloc géré `dsh-face`, juste avant le bloc `dsh-web`. |
| **Propriétaire** | walter-core (`core/engine`). Les valeurs appartiennent à l'instance : `walter instance config core engine.toml` (défaut neutre : `core/config/engine.toml`). |
| **État** | Actif depuis le 09/11/2026 (lot E1) : les lignes tenues à la main dans `/opt/dsh/home/profiles/web/cordis.patch.yml` ont été adoptées par le bloc rendu, configuration composée (`--dump-config`) identique avant et après. |
| **Ne fait pas** | Ne lance ni ne redémarre DSH ; ne touche pas aux préférences que DSH enregistre lui-même (thème, langue, avis d'accueil : état de l'utilisateur, ajoutées par DSH après les blocs gérés) ; n'écrase jamais une ligne écrite à la main pour les mêmes cibles (conflit explicite). |
| **Contrats** | Gabarit `dsh-face.patch.yml` (`${…}` remplacés par des scalaires JSON) ; valeurs `[dsh.web]` `name`, `tagline`, `cookie_max_age_days` (entier > 0) et `[dsh.model_names]` (noms affichés des tâches Walter Router) ; bloc `# walter:dsh-face` empreinté comme les autres sections gérées (`walter_platform/composition.py`). |

## Ce qui est rendu d'où

| Fichier de `DSH_HOME` | Source |
|---|---|
| `cordis.patch.yml` (racine) | `walter_platform/composition.py` + `core/compositions/dsh.json` ; noms affichés des modèles : `[dsh.model_names]` de l'instance ; rétention longue du cache de prompt dans la définition du fournisseur `walter` (avant le 09/11, ajoutée à la main) |
| `profiles/web/cordis.patch.yml` | bloc `dsh-face` (ce dossier + valeurs de l'instance), puis bloc `dsh-web` (`_dsh_web_profile`) ; ensuite les lignes que DSH ajoute lui-même |
| `profiles/headless/cordis.patch.yml` | bloc `dsh-headless` (`_dsh_headless_profile`) |
| `walter-hooks.json` | `_hook_data` + `core/compositions/dsh.json` |
| `profiles/*/cordis.yml` | racine vide écrite par DSH (`[]`), jamais modifiée |

## Reproduction depuis la source (09/11/2026)

Installation à partir d'un dossier vide comparée à l'installation en service (sorties `--dump-config`, chemin du
dossier neutralisé) : identiques à deux écarts près, tous deux sans effet sur le comportement :

- les préférences d'interface enregistrées par DSH (thème sombre, langue, version de l'avis d'accueil) ;
- `skill-filesystem` : la ligne est désactivée dans les deux cas, mais l'installation en service garde un ancien
  `customSkillDirs`.

## Changer une valeur

Modifier `@instance/config/core/engine.toml`, puis `walter harness install dsh` (aperçu) et `--apply`. Ensuite
régénérer le manifeste du gel (`engine/kernel/verify.py snapshot /opt/dsh --home /opt/dsh/home`) : l'empreinte du
fichier de profil change, celle de la configuration composée seulement si la valeur change réellement.
