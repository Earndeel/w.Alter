# Google Flow account check — verified sequence

## What was verified

On 2026-07-25, a fresh Google-cookie extract from the Mac Brave profile was
injected into a unique Camoufox Max session on `127.0.0.1:9377`. The French Flow
route loaded an authenticated Google Flow home page and showed the `PRO` profile
button. The first profile snapshot displayed `Chargement…`; after waiting and
requesting a new snapshot, the profile dialog exposed the exact UI label
`Crédits Google Flow` and a numeric balance. The observed balance was `1 035` at
that time; this is historical evidence, not a current balance.

## Request sequence

```text
GET  http://127.0.0.1:9377/health
POST http://127.0.0.1:9377/session/cookies
     {"userId": UNIQUE_USER_ID, "cookies": GOOGLE_COOKIE_LIST}
POST http://127.0.0.1:9377/tab/new
     {"userId": UNIQUE_USER_ID, "listItemId": "google-flow-check"}
POST http://127.0.0.1:9377/tab/navigate
     {"userId": UNIQUE_USER_ID, "tabId": TAB_ID,
      "url": "https://labs.google/fx/fr/tools/flow"}
POST http://127.0.0.1:9377/tab/snapshot
     {"userId": UNIQUE_USER_ID, "tabId": TAB_ID}
POST http://127.0.0.1:9377/tab/click
     {"userId": UNIQUE_USER_ID, "tabId": TAB_ID, "ref": PROFILE_BUTTON_REF}
(wait for the profile API/UI to settle; the first result may be `Chargement…`)
POST http://127.0.0.1:9377/tab/snapshot
     {"userId": UNIQUE_USER_ID, "tabId": TAB_ID}
POST http://127.0.0.1:9377/tab/close
     {"userId": UNIQUE_USER_ID, "tabId": TAB_ID}
```

Refs are regenerated on every snapshot. Select the profile button by its
current semantic name (`PRO`), never by a hardcoded ref from a previous tab.
Likewise, extract the balance from the refreshed snapshot by matching
`Crédits Google Flow` and its adjacent number.

## Cookie handling notes

- Copy the Brave `Cookies` database immediately before the check.
- Decrypt Google cookies on the host with the vault-provided Brave key.
- Keep cookie values out of logs, snapshots, assistant output, and saved
  references.
- Remove analytics cookies before injection; they are not needed for account
  authentication.
- A successful page load is not enough to prove the account balance: the
  profile dialog must finish its asynchronous load.

## Robust live-database backup over SSH

Do not `scp` Brave's live SQLite file directly while the browser may be writing.
Run Python on the Mac, open the source read-only, and use
`sqlite3.Connection.backup()` to create a temporary consistent copy; transfer
that copy, then delete it remotely.

macOS commonly invokes zsh for the remote command. `ssh` joins arguments after
the hostname into shell text, so a subprocess call shaped like
`[ssh, host, "python3", "-c", SOURCE]` can let zsh parse the Python punctuation.
Quote the complete Python payload and pass one remote command string:

```python
import shlex
remote = "python3 -c " + shlex.quote(python_source)
subprocess.run(["ssh", host, remote], check=True)
```

This is a transport/quoting rule, not a reason to abandon fresh-cookie recovery.
Never print the generated command when it embeds cookie rows or decrypted data.

## Read-only model-availability probe

The authenticated home-page carousel can expose new model branding before any
project is opened. Record the literal heading and button text from a live
snapshot. A heading such as `Introducing Gemini Omni Flash` with `Try Omni now`
proves account-level availability under that exact name, while consuming no
credits. It does **not** confirm the generation settings or cost: after prompt
approval, reopen the direct Create composer and verify model, duration, aspect
ratio and variant count immediately before submission.

## Cleanup and cost boundary

The verification path does not create a Flow project or submit a generation,
so it consumes no Flow credits. Close the temporary tab even after a failed
snapshot. Generation requires a separate explicit asset scope and should start
with a minimal validation render rather than a full batch.
