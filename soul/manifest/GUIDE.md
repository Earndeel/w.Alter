# walter-soul — guide détaillé

## Objectif

Donner à chaque runtime la même identité de W.Alter, les mêmes règles et le même profil de {{owner.address}}. Le logiciel
est neutre ; l'identité appartient à l'instance (`@instance/soul`, versionnée).

## Comment l'utiliser

`walter_profile()` renvoie le profil de {{owner.address}} (USER.md), l'identité et les règles de W.Alter rendues pour un
runtime neutre, et la mémoire critique (MEMORY.md). Court ; à charger en début de session quand la manière de
répondre ou les préférences de {{owner.address}} comptent et que le profil n'est pas déjà dans le prompt.

## Organisation

| Partie | Rôle |
|---|---|
| Moteur de rendu `walter-soul` | Compose identité + règles + adaptateurs de runtime ; `render`, `sync`, `check`, `init` |
| `runtimes/*.md` | Adaptateurs neutres par runtime (Hermes, Claude Code, Codex, DSH) |
| Instance `soul/{identity,rules}.md` | L'identité elle-même ; un commit lance `walter-soul sync` |
| Cibles | `SOUL.md` de Hermes (généré), profils `/opt/walter-profiles/*`, MCP `walter_profile` |

## Règles et limites

- `SOUL.md` est généré : modifier l'instance et committer, jamais le fichier rendu. `walter-soul check` détecte
  les modifications à la main.
- Une session ouverte hors des profils W.Alter (`/opt/walter-profiles/*`) est en mode technicien.
