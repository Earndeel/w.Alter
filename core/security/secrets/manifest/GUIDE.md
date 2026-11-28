# Walter Secrets — detailed guide

## Purpose
Give agents the use of {{owner.address}}'s complete Bitwarden vault without any secret value entering a model, a
journal, a prompt or a URL. An agent uses it to find a login, key or card and use it in a local command, or to
retrieve a code received by e-mail or Beeper.

## How to use it
1. `secret_search(query, kind)`: metadata and identifiers of entries, never a password, token, OTP or cookie.
   `kind` = login, card, identity, note, ssh_key.
2. `secret_reference(item, field)`: a `walter-secret://bitwarden/<uuid>/<field>` reference without value. A reference
   is a pointer, not an authorisation.
3. Local execution: `walter-secret exec --bind VAR=<reference> -- <command>`; the value exists only in the
   environment of the launched process, which inherits the harness's permissions. Its output is discarded.
4. Components read their API keys through grants (`@instance/accounts/<id>.toml`: `allow` = readers, `[env]` =
   variable name): `walter-secret grant env|exec --as <consumer>`.

## Organisation
| Part | Role |
|---|---|
| `walter_secrets/vault.py` | Bitwarden access, metadata, attachments, audit |
| `walter_secrets/service.py` | Model-safe v1 API (search, reference) and local execution |
| `walter_secrets/masking.py` | Shared masking, public errors without exception text |
| `walter_secrets/unlock.py` | Unlock from the local age-encrypted store (shared session) |
| `walter_secrets/otp.py` | Received codes: Gmail (Walter Memory connector), Beeper |
| `secrets_sync.py`, `vault_react.py` | Vault watching, application to targets, encrypted backup |
| `walter-secret grants` | W.Alter's authorisations per account and service |

## Interfaces
| Need | MCP | Local CLI |
|---|---|---|
| Find | `secret_search` | `walter-secret search` |
| Reference | `secret_reference` | `walter-secret ref` |
| Use | — | `walter-secret exec --bind …` |
| Grants | — | `walter-secret grants`, `walter-secret grant env|exec --as` |

## Rules and limits
- Never run `bw unlock` directly: the session is shared by `walter-secrets-sync`.
- Never a secret in a systemd unit, a URL, a command argument or an answer.
