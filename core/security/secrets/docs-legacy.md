# walter-secrets — W.Alter's access to Monsieur's Bitwarden

W.Alter uses **the whole** of Monsieur's Bitwarden vault on its own (decisions of 2026-10-02 and 2026-10-16: no
restricted Walter account), without a password or a code ever entering a model's conversation.

- Server: Vaultwarden `https://lucas-bitwarden.duckdns.org` (GCP VM `bitwarden`, project genai-470208, us-west1-b,
  Docker vaultwarden + caddy in `/home/lucas_jouvencon/vaultwarden`). SSH only through Tailscale (`100.95.19.10`) or,
  as a fallback, `gcloud compute ssh bitwarden --zone us-west1-b --tunnel-through-iap` from Cloud Shell.
- Account: Monsieur's (lucas.jouvencon@gmail.com). Unlock: `~/.hermes/bin/bw-unlock` (master password in the age
  vault `bitwarden/master_password`, session cached in `~/.hermes/vault/.bw_session_key`, 0600).
- Plugin enabled in Hermes since 2026-10-16 (`plugins.enabled` in `~/.hermes/config.yaml`).

## Files

| File | Role |
|---|---|
| `bwvault.py` | Vault access (cache, search, values, attachments to `/dev/shm`), placeholder `{{bw:<id or name>:<field>}}`, audit |
| `__init__.py` | Hermes plugin: `secret_*` tools + hooks (placeholders resolved at execution, values masked in every result) |
| `browser_bridge.py` | Filling web pages (password, TOTP, received code), account creation, 2FA key capture — anti-phishing origin check |
| `otp.py` | One-time codes received **by e-mail** (Gmail read-only) **or by message** (Beeper: WhatsApp, Telegram, LINE, Messenger, Instagram) |
| `secrets_sync.py` | Vault watcher (`watch`) + application of W.Alter's keys to the VM (env files, age vault) |
| `vault_react.py` | Reactions to a vault change: filing new entries into folders, encrypted backup |
| `walter-secret` | CLI (`/usr/local/bin/walter-secret`), root only |
| `walter-secrets-sync.service` | Template of the systemd unit installed as `/etc/systemd/system/walter-secrets-sync.service` |

## Hermes tools

| Tool | What it does |
|---|---|
| `secret_search(query)` | Find an entry (metadata only) → handle `bw:<id>` |
| `secret_fill(handle, field="password"\|"totp")` | Fill the password or the TOTP code into the page — refused if the page is not one of the entry's sites |
| `secret_otp(site, since_minutes=10, timeout=120)` | Wait for the code the site sent by e-mail / message and fill it (same origin check) |
| `secret_create_login(username, …)` | Generate a password, save the entry **before** submitting, fill the sign-up form |
| `secret_capture_totp(handle)` | Read the 2FA key shown on the page and store it in the entry |
| `secret_file(handle, name)` | Decrypt an attachment to `/dev/shm/walter-secrets` (deleted after 2 h) |
| `secret_reveal(handle, field)` | Value in the conversation — **last resort** |

Agent procedure: skill `bitwarden-logins` (decision tree per kind of code, addy.io aliases for sign-ups).

## CLI

```
walter-secret get <id|name> <field>          value (used by {{bw:…}} placeholders in terminal commands)
walter-secret search [words…]                metadata only
walter-secret file <item> [attachment]       attachment → /dev/shm, prints the path
walter-secret otp <site> [minutes] [timeout] received code — use it inside $( … ), never print it
```

## Codes received by e-mail / message (`otp.py`, 2026-10-17)

Only messages received after `since` (10 min by default) **and** mentioning the site are read; the code is extracted
(keyword nearby, 4–8 digits, 6 preferred, dates / years / order numbers rejected). Sources: Gmail via the Walter
Memory token (`/root/.hermes/raw-vault/google-walter-memory.json`, gmail.readonly) and the Beeper Client API on the Mac
(`http://100.127.150.1:23373`, token `vault get beeper/token`).
**Limit: no real SMS** — Beeper has no SMS account. Real SMS codes: ask Monsieur.

## Vault watcher (`walter-secrets-sync.service`, 2026-10-16)

Every 30 s, one request `GET /api/accounts/revision-date`. On a change:
1. W.Alter's keys (folder « W.Alter – Clés API ») modified in Bitwarden → applied to the VM (`.env`, service env
   files, age vault; backup + targeted restart + automatic rollback). Deletions are never propagated.
2. New entries (no folder or « W.Alter – Comptes créés ») → filed: card / identity / SSH → `01`; site already filed
   → same folder (majority ≥ 60 %); otherwise Walter Router's decision model (`llm.decide`, name + domain only,
   names pseudonymised; confidence < 0.6 → left in place). Only `folderId` changes, checked after each move.
3. Event `vault.changed` on the Walter bus.
4. After 2 min of calm: encrypted export (age, recovery key) → `~/.hermes/backups/bitwarden/vault-*.json.age` + Drive
   `W.Alter Backups/bitwarden` (local: everything < 48 h, then one per day for 14 days).

State: `~/.hermes/logs/walter-secrets-sync.status.json`; log: `~/.hermes/logs/walter-secrets-sync.log`.
Manual: `vault_react.py file --dry` (simulation), `vault_react.py backup`.

## Vault organisation (2026-10-16)

14 thematic folders `01 · Identité, documents & clés` … `14 · Comptes de tiers` + `W.Alter – Clés API` (W.Alter's keys,
read by `secrets_sync`). addy.io aliases: key in « W.Alter · addy » (id `5de2210f-5f2e-45bc-8527-81c54760dc84`).

## Security

- Audit: `~/.hermes/logs/walter-secrets.jsonl` — action, entry, field, origin, channel; **never a value or a code**.
- Masking: every known value (and every value resolved in the process) is replaced by its placeholder in tool results
  and terminal output.
- Anti-phishing: password, TOTP and received code are only filled on the entry's site / the named site.
- Backups: nightly `walter-offsite-backup` (including the vault) + monthly restore test (≥ 100 entries checked).
- Known weak point (accepted by Monsieur): the master password is on the VM (age vault whose key sits next to it);
  a compromise of the VM gives access to the whole vault.

## History

DECISIONS.md (`~/.hermes/docs/walter-memory/`): 2026-10-02 (autonomous access, sync), 2026-10-16 (Vaultwarden
hardened, folders, addy, watcher, backups, `llm.decide` on the router), 2026-10-17 (received codes).
