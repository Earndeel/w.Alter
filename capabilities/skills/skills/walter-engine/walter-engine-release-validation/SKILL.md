---
name: walter-engine-release-validation
description: Use when applying Walter Engine runtime changes, reloading its production configuration, deploying Portal assets, or validating persistent Python kernel behavior on Monsieur's VM.
---

# Validate a Walter Engine release

## Establish the live runtime and rollback

Read the current engine README, release/migration notes and rollback record before acting. Resolve the core path with `walter path core`. Verify the actual systemd unit and process; do not infer production from old documentation. Since the native-engine switch of 2026-11-17, the observed production unit is `walter-engine.service` (`walter-python -m walter_engine serve`); `dsh-web.service` is masked. Never unmask or resurrect a retired runtime for a visual deployment.

Back up affected files under the instance's backups/changes directory. Record hashes and reject concurrent edits. Parse the effective instance TOML and check selected nonsecret settings: duplicate tables can cause a silent fallback to neutral configuration. Keep other agents' changes.

## Decide whether a restart is necessary

Native Portal assets live under `core/engine/walter_engine/ui`. The native web server reads them with FileResponse for each request; index uses no-store and assets no-cache. Pure HTML/CSS/JS updates need a browser reload, not an engine restart. Preserve app.js when the change is only presentation. Verify the current server implementation before relying on this behavior.

If runtime/config changes require a restart, identify idle state first: unit start time, current engine activity, open-run state, active `walter-python-*` kernel units, and recent lifecycle events. On the native engine, aggregate journal `turn/start`/`turn/end` and session principal metadata without printing message contents. An unclosed turn may be a technical test awaiting approval; distinguish it from a real owner workload. A running service alone is not evidence that it is idle. Do not kill a real user turn or kernel workload merely to finish validation; defer or coordinate the interruption.

## Apply and verify the intended behavior

Reload only the active unit if required. Verify active/running and its current start timestamp, then the actual web/API endpoints. Keep authorization enabled: an anonymous 401 may prove the host fence accepts the expected Host; it does not prove an authenticated UI works.

For public Portal QA, use `browser_session(site, session, engine)` and `walter-browser` to drive the approved authenticated browser. Never extract cookies/signing keys or forge sessions. Test desktop/mobile, actual controls and errors without exposing private conversation contents. A theme check does not require sending a real user message.

For kernel/PATH changes, test through the documented Engine API or production conversation interface, not a host-shell substitute. An explicit technical test can ask the python tool to run `bash('python --version && which python pip')`. Inspect the execution trace and interpreter paths. For persistence/recovery claims, test across turns or a controlled restart separately; one successful call does not establish recovery.

## Clean up and record

If an end-to-end test creates durable tasks, compare tasks_list before/after and close only positively identified technical-test tasks with task_update and a note. Do not assume labels such as test or e2e isolate tasks on every historical runtime; verify the live implementation. Never close real mission follow-up as test cleanup.

Record the changed files, backup, restart (if any), browser/HTTP results, actual kernel output when relevant, test-task cleanup and limitations. Keep service availability, UI validation and model/tool execution as separate claims. For a failure, follow the documented rollback without restoring unrelated state or reviving a retired engine.
