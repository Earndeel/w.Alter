---
name: walter-memory-policy-rollout
description: Use when changing Walter Memory's cloud reasoning policy and verifying that previously filtered knowledge reaches model calls and injected context without weakening credential masking or outbound disclosure controls.
---

## Establish the authorized policy

Read the current architecture, dated decisions and effective Memory configuration before editing. Treat the owner's authorization as specific to the requested change; do not infer permission to broaden cloud access from this procedure.

Distinguish three decisions: what the model may read, what an outbound message may disclose, and which credential values must be masked. Preserve privacy classifications and evidence metadata when changing access policy.

## Inventory the complete path

Resolve the module root with `walter path memory`, then inspect Git status and existing diffs. Back up touched files under the instance's `backups/changes/` before modifying them. Preserve unrelated edits.

Find restrictions across producers, readers and model calls:

```bash
rg -n 'local_only|redacted_cloud|cloud_allowed|cloud_readable|model_may_receive|pseudonym|mention_policy|disclosure_state' walter_memory connectors ports config tests
```

Inspect at least `privacy.py`, `read_policy.py`, `llm.py`, `agent_memory.py`, `search.py`, `context.py`, `episodes.py`, `episodic.py`, `periods.py`, `views.py`, extraction and Kardex enrichment. Check effective instance overrides with `walter instance config memory organic.toml`.

Do not assume changing the main context reader changes extraction, reranking, episode generation or model-call admission.

## Keep admission, transformation and disclosure separate

Check whether `cloud_readable()` answers a reader-policy question while `model_may_receive()` admits a payload that will be transformed before transmission. A `redacted_cloud` payload can require admission followed by masking; conflating these predicates caused model calls to fail during the observed rollout.

For Kardex, inspect every visibility gate. An authorized full-reasoning exception may need to pass sensitivity and mention-policy checks while retaining disclosure annotations. Passing one gate does not guarantee the claim reaches the model. Keep third-party disclosure enforcement separate.

Mask credential values within messages rather than discarding whole messages when the authorized policy permits retaining their surrounding meaning.

## Recompute knowledge skipped under the old policy

Inventory extraction segment statuses, policy refusal markers, derived-item generations, view statuses and search-index coverage using counts and timestamps. Avoid dumping personal contents into the transcript.

Identify the exact refusal or completion markers that prevent retries. Reset only those affected by the policy change, through the supported processing interface where available. Do not blindly reset all extraction state or assume restarting services reprocesses skipped inputs.

Rebuild affected plans, episodes, periods, views and indexes in dependency order. Preserve generation and shadow controls; cloud-read authorization does not authorize switching the active generation.

## Verify actual model use

Run the Memory suite from the module root:

```bash
walter-python -m pytest -q -p no:cacheprovider tests
```

Investigate failures against the intended policy contract before changing assertions. Check that default and restrictive configurations still behave as specified.

Exercise the existing demonstration with a real cloud model:

```bash
walter-python bench/demo_v1.py everything --out "$(walter instance path state)/memory/demo-v1"
```

Confirm the current CLI and output path before running. Require evidence that previously excluded knowledge enters the injected context and supports an answer with tools disabled. A successful database read or service health check is insufficient.

If an answer still lacks accessible knowledge, inspect context trace section budgets and candidates, derived-item index coverage, period selection and overview truncation. In the observed rollout, flow observations lacked search coverage and period overview truncation hid later sections. Preserve headings and allocate space across sections when shortening summaries.

## Activate and record

Restart only affected services and verify fresh processing timestamps and refusal counts. Use `hermes gateway restart` if Hermes must reload the change. An active service does not prove processing progress.

After changing Memory services, run:

```bash
systemctl start memory-autopilot
```

Inspect its latest score and findings. Append the authorized policy, validation evidence and remaining limitations to `DECISIONS.md`. Review the staged diff and commit only the intended changes, especially when files already contain edits from other sessions.
