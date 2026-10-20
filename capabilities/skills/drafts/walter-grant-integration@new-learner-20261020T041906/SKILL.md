---
name: walter-grant-integration
description: Use when migrating a Walter consumer from direct credential files or another runtime's environment to walter-secrets grants, or diagnosing grant integration health.
---

## Inspect the existing authorization

- Read the walter-secrets grant implementation and an existing account card before changing a consumer. Locate the module with `walter path secrets`; locate instance-owned configuration through `walter instance`, without hardcoding an instance directory.
- Run `walter-secret grants` and `walter doctor`. Treat metadata health and successful authenticated access as separate checks.
- Identify the credential owner, consumers, scopes, storage reference and sole refresh-token writer. Preserve that writer; sharing an access token must not introduce a competing refresh loop.
- Inspect credential field names and file permissions without printing values. Never dump access-token command output into logs.

## Migrate one consumer

- Back up changed files under `/root/.hermes/backups/` and inspect git status before editing.
- Reuse the existing grant when it represents the same authorization. Keep account-specific metadata in the instance's account cards, outside neutral module code.
- Replace direct credential-file or runtime-environment reads with the declared grant interface. Python consumers can use `from walter_secrets import grants` and `grants.access("<grant-id>")`; inspect the implementation for supported token parts and return types before adapting callers. The command interface is `walter-secret grant access <grant-id>`; capture its output privately if needed.
- Remove obsolete token caches, refresh logic and imports only after confirming that the grant interface supplies their required behavior.
- Keep credential files mode 0600 and their private directories appropriately restricted. Check symlink targets with `stat -L` before interpreting permissions.

## Verify functionality and generated metadata

- Run the affected module's tests and a minimal authenticated read using the actual consumer. Check only success, status and non-sensitive metadata. Do not send a message merely to test authorization.
- Restart only affected services, then inspect their health and recent logs for authentication or refresh failures.
- If a contract changed, regenerate the registry and generated contract documentation from the core repository:
  ```sh
  walter contracts render > modules/registry.json
  walter contracts render --format markdown > docs/contracts.generated.md
  walter doctor
  walter check
  ```
- Inspect failed tests individually. A green doctor result does not establish that the test suite passed.
- After changing memory connectors, run `systemctl start memory-autopilot`, wait for completion and inspect the summary in `/root/.hermes/logs/memory-autopilot/latest.json`.
- Search active consumer code for the retired credential references, distinguishing active reads from documentation and backup manifests. Record remaining consumers and validation evidence before committing.

## Pitfalls

- A modified contract can leave the generated registry stale and make `walter doctor` fail until regeneration.
- Separate token copies can look equivalent while having different ownership or renewal semantics. Compare them privately if necessary; never print them.
- Reading a CLI-managed rotating refresh token does not authorize another component to refresh it.
- Do not expand credential migration into changes to unrelated services without authorization.
