# File Safety Deny Lists (as of v0.14.0+)

Source: `agent/file_safety.py` on `origin/main`.

## Read-deny (`get_read_block_error`)

Blocks `read_file` tool on these paths under BOTH `_hermes_home_path()` and `_hermes_root_path()`:

**Credential stores (exact file match):**
- `auth.json` — provider OAuth state + plaintext API keys
- `auth.lock` — lockfile
- `.anthropic_oauth.json` — Anthropic PKCE tokens
- `.env` — provider API keys
- `webhook_subscriptions.json` — per-route HMAC secrets

**Credential directories:**
- `mcp-tokens/` — OAuth token directory (dir + everything inside)

**Cache files (directory match):**
- `skills/.hub/` — prompt-injection carrier metadata
- `skills/.hub/index-cache/`

**Bypass:** `terminal` + `cat` still works. The deny is defense-in-depth against LLM `read_file` calls, not a hard security boundary. The docstring explicitly states: *"This is NOT a security boundary. The terminal tool runs as the same OS user."*

## Write-deny (`is_write_denied`)

Blocks `write_file` / `patch` on:

**Control-plane files (added in PR #14157, #17656):**
- `auth.json`
- `config.yaml`
- `webhook_subscriptions.json`
- `mcp-tokens/` (directory + contents)

**Credential stores:**
- `.env` (both active profile and root)

**System files:**
- `.ssh/authorized_keys`, `.ssh/id_rsa`, `.ssh/id_ed25519`, `.ssh/config`
- `.bashrc`, `.zshrc`, `.profile`, `.bash_profile`, `.zprofile`
- `.netrc`, `.pgpass`, `.npmrc`, `.pypirc`
- `/etc/sudoers`, `/etc/passwd`, `/etc/shadow`

**Directory prefixes:**
- `.ssh/`, `.aws/`, `.gnupg/`, `.kube/`, `.docker/`, `.azure/`
- `.config/gh/`
- `/etc/sudoers.d/`, `/etc/systemd/`

## Workflow implications for us

| Operation | Tool | Blocked? | Workaround |
|---|---|---|---|
| Read `.env` | `read_file` | ✅ Blocked | `terminal` + `cat ~/.hermes/.env` |
| Read `auth.json` | `read_file` | ✅ Blocked | `terminal` + `cat` |
| Patch `config.yaml` | `patch` | ✅ Blocked | `terminal` + `sed` or Python script |
| Read vault.json.age | `read_file` | ❌ Not blocked | Direct (different path) |
| Read age-key.txt | `read_file` | ❌ Not blocked | Direct (different path) |
| Write skills | `write_file` | ❌ Not blocked | Direct |
| Patch scripts | `patch` | ❌ Not blocked | Direct |

## chmod guard

`secure_parent_dir()` refuses to `os.chmod` `/` or any directory at depth < 2. Prevents bricking the host if HERMES_HOME resolves to `/`.
