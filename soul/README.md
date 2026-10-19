# walter-soul

Rend l'identité de l'agent de l'**instance active** pour chaque runtime (Hermes, Claude Code, Codex, DSH, MCP
`walter_profile`). Logiciel identique pour toutes les instances : aucune identité de personne ici.

| Logiciel (ce module) | Instance (`walter instance path`) |
|---|---|
| `bin/walter-soul` — moteur de rendu | `soul/identity.md`, `soul/rules.md` — identité et règles (git ; le hook post-commit lance `walter-soul sync`) |
| `runtimes/*.md` — adaptateurs par runtime, neutres (`{{owner.address}}`…) | `soul/runtimes/<runtime>.md` — ajouts propres à l'instance (facultatif) |
| `defaults/` — identité et règles d'une nouvelle instance (`walter-soul init`) | `profile/USER.md` — profil curé (`{{include profile}}`) |
| `config/targets.toml` — sources et cibles par défaut (`@instance/...`) | `config/soul/targets.toml` — surcharges (ex. emplacements historiques d'un harness) |
| | `state/soul/` — empreintes ; `backups/soul-drift/` — retouches manuelles conservées |

Commandes : `walter-soul render|path <cible>`, `sync [--force]`, `check`, `init`. Les marqueurs `{{owner.*}}` et
`{{instance.id}}` sont remplis par `walter instance render`.
