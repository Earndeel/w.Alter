# Hermes operations branch checklists

## Target freeze

Record active `HERMES_HOME`, profile, checkout, interpreter, config, process owner, endpoint, browser session, account/tenant, task identity, and rollback input before mutation. Re-read each after the change.

## Browser and human handoff

Check supervisor and live browser health separately. Keep one canonical session, serialize restarts, refresh semantic state after navigation, and bind coordinate evidence to the newest target geometry. Under manual intervention, pause agent writes, acquire a session lock, revoke it before resuming, and re-check URL, tab, identity, health, and screenshot.

## Durable Computer Use

Keep schema, approvals, dispatch, lifecycle, capture, and result shaping in the host. Extensions provide named strategy/backend selection and compatibility checks. Fail closed on missing contracts; distinguish transport acceptance, UI state, and task postcondition; return no-target or needs-user-input without speculative actions.

## Remote repair

Verify hostname, IP, cloud scope, service, mounts, and process owner. Snapshot or export first, use a temporary least-privilege path, bind secret-bearing services privately, change only the named component, test real login/sync/decryption/display, and remove temporary access.

## Read-only Hermes profile audit

1. **Freeze the target.** Run `hermes profile show <name>` first; record its exact profile path, configured model/provider, alias, and reported gateway state. Use `-p <name>` on every subsequent Hermes command so a shell default cannot silently redirect the audit.
2. **Inspect declared intent without exposing secrets.** Read the target profile's `config.yaml`, `SOUL.md`, `memories/USER.md`, and `memories/MEMORY.md`. Parse YAML for selected non-secret fields when needed. Inspect `.env` key names only; never print values or dump `auth.json` into output. Use `auth list` only when credential status matters, and redact identifiers from the report.
3. **Collect live evidence separately.** Run `hermes -p <name> status`, `hermes -p <name> doctor`, and `hermes -p <name> prompt-size --json`; inspect `skills list` and `tools list` for actual enabled scope. Add `mcp list` or `auth list` only when those integrations matter. Status, doctor, and prompt-size answer different questions; none substitutes for the others.
4. **Reconcile config with the effective behavior.** Treat doctor warnings, environment overrides, YAML types, and CLI-reported values as distinct evidence. A JSON-looking quoted scalar is still a YAML string and may be ignored where a list is expected. A generic `config get` warning can reveal an unrecognized key; verify its effect with the relevant feature-specific listing. When profile and skill inventory counts disagree, report both rather than guessing which is authoritative.
5. **Audit safety independently of persona.** Compare `SOUL.md` instructions with `approvals.mode`, terminal backend, enabled tools, and security flags. `approvals.mode: off` disables terminal safety prompts/checks; treat it as high risk unless the trusted sandbox boundary is verified. A persona's promise of unrestricted answers is not an enforcement mechanism and does not override provider/platform policy.
6. **Separate readiness from configuration.** Check whether the gateway is actually running, the target platform is configured, sessions are active, and scheduled jobs exist. A listed plugin or credential proves configuration/presence, not a healthy live connection. Distinguish profile-local faults from installation-wide alerts such as credentials duplicated across other profiles; do not attribute cross-profile findings to the target without evidence.
7. **Report a prioritized, read-only verdict.** Lead with whether the profile is usable for its intended path, then list safety, reliability, availability, and footprint findings with exact command evidence. Explain a non-zero doctor exit by naming its findings; do not imply the primary model is unavailable unless its own route failed. Make no configuration changes unless explicitly requested, and state any unresolved uncertainty.
