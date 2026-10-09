# Autonomous job completion verification

Use this reference when a scheduled or manually launched autonomous job can mutate durable state or invoke an external model.

## Procedure

1. Snapshot the durable state and record the exact configuration, model/provider, and code revision before running.
2. Verify the provider by resolving the configured model and observing one real request's endpoint, model ID, and reasoning parameters without exposing credentials.
3. Run the smallest real job that exercises the target path with a bounded timeout; use a dry run only for preview, never as completion evidence.
4. Inspect the job's durable report, not only its process exit code. Require: no provider error, no guardrail halt, forward progress, expected mutation counts, and ledger/archive evidence for every destructive-looking transition.
5. Read back the target state and verify source preservation, references/routing, and rollback artifacts. Treat archived content as recoverable, not as inline availability.
6. If the job stops on a repeated failed read or tool call, stop that branch and change strategy; do not replay the same request until the tool-call budget is exhausted.

## Completion gates

- A successful transport/exit status is insufficient when the worker can catch errors internally.
- A summary claiming consolidation is insufficient without durable ledger declarations and content-preservation checks.
- A timeout or quota error is a failed validation, not a successful no-op.
- Do not launch a second mutation pass merely to obtain a prettier report; first repair the reporting or routing defect and rerun the bounded verification.
