# Bitwarden Secrets Manager (BWS) — Hermes Native Integration

Added in Hermes v0.14.0 (PR #30035, 2026-05-21). **We do NOT use this** — see below for why.

## What it does

Pulls API keys from Bitwarden Secrets Manager at Hermes startup, replacing plaintext `.env` entries. One bootstrap token (`BWS_ACCESS_TOKEN`) replaces N per-provider keys. Rotations take effect on next restart.

## Commands

```bash
hermes secrets bitwarden setup      # interactive wizard
hermes secrets bitwarden status     # config + binary + token state
hermes secrets bitwarden sync       # dry-run fetch
hermes secrets bitwarden sync --apply  # actually export to env
hermes secrets bitwarden disable    # flip enabled: false
hermes secrets bitwarden install    # just download bws binary
```

## How it works

1. `bws` binary auto-downloads to `~/.hermes/bin/bws` (v2.0.0, SHA-256 verified)
2. At startup, reads `BWS_ACCESS_TOKEN` from env or config
3. Fetches all secrets from BSM
4. Overwrites matching env vars by default (`secrets.bitwarden.override_existing: true`)
5. Failures emit a warning but never block startup — falls back to existing `.env`

## Config in config.yaml

```yaml
secrets:
  bitwarden:
    enabled: true
    override_existing: true  # BSM overwrites .env values
    access_token: ""         # or set BWS_ACCESS_TOKEN env var
```

## Why we don't use it

Our Bitwarden instance (`lucas-bitwarden.duckdns.org`) is a **self-hosted Personal Vault**, accessed via the `bw` CLI. BWS (Secrets Manager) is a separate product that requires:
- An organization with Secrets Manager enabled
- Service accounts with access tokens
- Secrets explicitly assigned to projects/service accounts

Our credential chain: `vault.json.age` (source of truth) → `.env` (runtime) → `bw` CLI (backup/fallback) → `walter-vault` broker (unified resolver).

## When to consider activating

If Monsieur wants to centralize ALL Hermes API keys in Bitwarden and eliminate `.env` entirely:
1. Enable Secrets Manager on the Bitwarden org
2. Create a service account, get `BWS_ACCESS_TOKEN`
3. Assign secrets to the service account's project
4. Run `hermes secrets bitwarden setup`
5. Then `hermes secrets bitwarden sync --apply`
6. Set `override_existing: true` so BSM is source of truth
