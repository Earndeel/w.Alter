# Walter Secrets

Shared vault access for Walter's clients. The core imports with Python 3.11+ alone;
Hermes, DSH, Codex and Claude Code are **not** Python dependencies of the core.

## Ownership and boundaries

- `walter_secrets/vault.py`: Bitwarden access, metadata, attachments, audit.
- `walter_secrets/service.py`: version 1 model-safe metadata/reference API and local-only execution.
- `walter_secrets/masking.py`: shared redaction, safe public error responses.
- `walter_secrets/unlock.py`: bootstrap from the existing age-encrypted local vault;
  passes the master password to `bw unlock` in an environment variable, never argv.
- `walter_secrets/otp.py`: received-code sources. Gmail uses Walter Memory's Google connector;
  Beeper uses its local client API. These are optional operational dependencies.
- `walter_secrets/secrets_sync.py`, `vault_react.py`: watcher, target application, encrypted
  backup and folder classification. They consume Walter Memory's bus/decision interfaces.
- `walter_secrets/ports/hermes/`: tool/hook registration and native browser integration.
  The browser port uses Hermes' page session, field classifier and protected evaluator;
  it is intentionally a host adapter, not a falsely portable browser API.
- `compat/`: legacy import and command launchers. Existing LLM gateway and backup callers
  resolve to the same package, rather than independent copies of vault logic.

No upstream Hermes files are patched. Its installed plugin entrypoint is a small adapter.
`config/walter-secrets.toml` holds the shipped defaults (paths in the active instance, no
vault server, no names). The instance's `config/secrets/walter-secrets.toml` (`walter instance
config secrets walter-secrets.toml`) binds its vault server and account, storage, backup remote,
owner names and service consumers; an instance may keep historical encrypted locations there.
`WALTER_SECRETS_CONFIG` selects another configuration explicitly. Paths accept `~/...` and
`@instance/...`.

## Public API

```python
from walter_secrets.service import search, reference
from walter_secrets.masking import public_error

# Metadata, no password/code/hidden field values; URI credentials/query/path removed.
result = search("example", kind="login", limit=20)
# Read the item's metadata to validate a field; does not retrieve its value.
ref = reference("bw:<item-id>", "password")
```

`search` returns `{api_version, items, usage}`. `reference` returns
`{api_version, reference, item_id, field, value_disclosed:false}`. An address such as
`walter-secret://bitwarden/<uuid>/field%3Aapi_key` is a value-free pointer, **not** an
authorization token. Use these APIs as MCP tools; never export `Vault.value`, the raw CLI
commands or arbitrary `execute` as generic MCP tools. Exceptions crossing that boundary
must go through `public_error` (it deliberately omits exception text).

## Local execution for any harness

```text
walter-secret ref <item-id> password
walter-secret exec --bind API_KEY=walter-secret://bitwarden/<uuid>/field%3Aapi_key -- /path/to/local-client
```

The client reads its bound environment variable inside the local process. `exec` uses
`shell=False`, inherits the calling harness's sandbox and permissions, and returns only
success, exit code, timeout state and binding count. It always discards stdout/stderr:
masking cannot guarantee removal of arbitrarily transformed credentials. No command is
run by MCP, and no extra permission bypass is introduced. A timeout terminates the child
process group. Command paths/arguments must themselves contain no raw secrets.

Legacy `get`, `file` and `otp` CLI commands remain for local programmatic consumers.
`get` and `otp` return raw values and must **never** be invoked directly into an agent's
captured terminal output. Existing Hermes placeholder hooks still perform local resolution
and redact tool output. Other harnesses do not inherit those hooks; use `exec` there.
Hermes' pre-existing `secret_reveal` remains in that host's legacy port only; it is not part
of the shared safe API and is not registered in Walter MCP.

`Masker` can protect accidental echoes (registered values, selected transport encodings,
short OTPs); it cannot replace output suppression for arbitrary code. `public_error` is
suitable for errors involving secret-bearing subprocesses and HTTP requests.

## Operation and validation

`walter-secrets-sync` retains its existing service and graceful-restart behavior. Its
Hermes restart command is now a declared consumer binding, not hardcoded in shared logic.
No key or account rotation, vault item edit, login or signup is part of this extraction.

Tests use fake vault entries and credentials only. They verify import without any host,
no-value metadata/references, execution and timeout, masked hooks, registration parity,
bootstrap argument hygiene and configurable consumer restart. Run:

```text
PYTHONPATH=. python -m pytest -q tests
```

Additional source dependency: the watcher uses Walter Memory's bus/decision library at
its configured module path; the age, bw and rclone executables are system dependencies.
Folder classification may call its configured model through Walter Memory; no model is
hardcoded here. The operational history of the first deployment is kept with that instance, not in this module.

## Autorisations (grants)

`walter_secrets.grants` tient le registre des autorisations de Walter : ses propres identités (bot Telegram,
abonnement Codex, client Google Cloud, tunnels) et les accès délégués aux comptes du propriétaire (Gmail/Agenda,
Beeper, Drive, cookies de navigation). Une fiche par autorisation dans `accounts/<id>.toml` de l'instance (sans
secret : propriétaire, nature, droits, consommateurs, responsable du renouvellement) ; le secret est au coffre
(`vault:<item>#<champ>`) ou, tant qu'il est à son emplacement historique, dans un fichier privé déclaré
(`file:<chemin>[#clé.json]`). Les modules demandent `grants.access(id)` ou `walter-secret grant access <id>` ;
seul le responsable déclaré renouvelle (OAuth ici, CLI du fournisseur pour Codex et rclone). Santé, sans valeur :
`walter-secret grants`.

