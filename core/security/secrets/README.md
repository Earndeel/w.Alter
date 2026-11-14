# Walter Secrets

| | |
|---|---|
| **Rôle** | Accès partagé au coffre Bitwarden du propriétaire : références au coffre et injection locale des valeurs autorisées, sans qu'aucune valeur n'entre dans un modèle. |
| **Propriétaire** | walter-secrets (`/walter/core/security/secrets`). |
| **État** | **active** (constat du 11/11/2026) : service `walter-secrets-sync` ; clés d'API des composants par autorisation (`allow` + `[env]`), plus aucun fichier de clés global. |
| **Ne fait pas** | Donner une valeur secrète à un modèle, un journal, un prompt ou une URL ; exporter `Vault.value`. |
| **Contrats** | [contracts/secrets.json](contracts/secrets.json), [contracts/maintenance.json](contracts/maintenance.json) ; MCP `secret_search`, `secret_reference` ; CLI `walter-secret`. |

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

`walter-secrets-sync` retains its existing service and graceful-restart behavior. Consumer
restarts are declared bindings (`[[env_consumers]]` of the instance), not hardcoded in shared logic; the Hermes
binding was removed with `~/.hermes/.env` on 2026-11-11.
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

### Clés d'API par autorisation — source unique (2026-11-11)

Depuis le retrait de `~/.hermes/.env` (décision du propriétaire, 2026-11-11), **chaque clé d'API qu'un composant
utilise a une fiche** et une seule source : son champ Bitwarden. La fiche déclare :

- `allow = ["llm", "router", …]` : les composants autorisés. Dès qu'une fiche a `allow`, toute lecture nomme son
  lecteur (`grants.access(id, consumer=…)`, `walter-secret grant access <id> --as <composant>`) ; les autres sont
  refusés, et chaque lecture est journalisée (fiche, champ, lecteur ; jamais la valeur). Tous les processus tournent
  sous le même utilisateur : c'est un contrat appliqué et tracé, pas une barrière du système.
- `[env] NOM = "<partie>" | "attribute:<clé>"` : le nom sous lequel un composant connaît le secret (configuration
  de fournisseurs, outil tiers). `grants.env_value(NOM, consumer)` le résout ; **aucun repli** vers un fichier,
  l'environnement global ou Hermes : sans fiche ou sans droit, l'appel échoue.
- `[attributes]` : valeurs non secrètes rangées avec l'autorisation (identifiant de compte, e-mail de connexion).

Les lectures statiques (clés, attributs) restent en mémoire du processus 15 min (`CACHE_S`), jamais sur disque ; le
CLI `bw` sert son cache local chiffré quand Vaultwarden ne répond pas. Pour un outil tiers qui ne lit que son
environnement, l'injection est ciblée : `walter-secret grant exec <id>[,<id>…] --as <composant> -- commande…` ajoute
uniquement les variables `[env]` de ces fiches, puis remplace le processus (aucun fichier écrit). L'aide
`bin/walter-cloudflare` (sur le PATH) en est l'exemple : fiches `cloudflare-api` et `cloudflare-workers-ai`, lecteur
`walter-cloudflare`, `walter-cloudflare check` échoue si une valeur manque.

Fiches de l'instance au 11/11 : `openrouter` (llm, router, memory), `kie`, `arnict`, `venice` (llm, router),
`cloudflare-api` (walter-cloudflare), `cloudflare-workers-ai` (memory, router, walter-cloudflare). La synchro
`walter-secrets-sync` ne génère plus aucun fichier de clés global : elle tient le coffre de démarrage chiffré (age) et
les seuls fichiers d'environnement déclarés par l'instance (`[sync] env_files`, aujourd'hui le canari de contrôle).
`mapping.entry()` (carte par valeur) ne sert plus aux clés d'API des composants.
Toutes les valeurs Cloudflare sont dans l'item « W.Alter · cloudflare » (champs `ai_token`, `email` ajoutés le 11/11).
`nordvpn` (jeton d'accès du compte Nord, lecteur `browse`, champ masqué `access_token` de l'item « nordaccount.com »),
installée le 11/11 : 18 fiches.


## Abonnement Claude

Une autorisation `subscription` de fournisseur `anthropic-claude`, responsable `walter-secrets`, peut conserver une session compatible CLI dans un fichier privé déclaré. L’accès est servi par `grants.access` comme les autres autorisations. Le jeton opaque utilise `claudeAiOauth.expiresAt` (millisecondes) ; le refresh PKCE public est effectué sous verrou interprocessus. Access token, refresh token et expiration sont remplacés atomiquement en 0600. Le CLI consommateur ne reçoit que l’access token en environnement et ne doit pas renouveler ce fichier. La santé expose uniquement l’expiration et la présence du refresh token. Aucun nouveau secret n’est exposé dans MCP.

## Empreintes du coffre (masquage dans les journaux)

`walter_secrets.fingerprints` tient un index **sans aucune valeur** des secrets du coffre : HMAC-SHA256 (clé locale
aléatoire `@instance/state/secrets/fingerprint.key`, 0600) tronqué à 128 bits, plus les longueurs
(`@instance/state/secrets/fingerprints.json`, 0600). Indexés : mot de passe et graine TOTP, champs personnalisés
texte/masqués, numéro et code de carte, numéros d'identité ; ignorés : valeurs avec espaces, de moins de 8 caractères,
courtes à une seule classe de caractères, e-mails, URL, booléens, notes. `fingerprints.scrub(text)` remplace toute
valeur connue par `«secret:vault»` (rien sans index). Reconstruit par `secrets_sync watch` à chaque révision du
coffre et toutes les 6 h ; à la main : `walter-secret fingerprints build|status`. Consommateurs : walter-logs
(`walter_memory.logs.mask`) et la porte d'écriture de `core.events` (`events.record_events`). Origine : 2026-10-30,
une clé Kie hexadécimale collée dans un chat était écrite en clair dans `walter_logs`.
