# CLI provider and multimodal evaluation

## CLI-backed providers

- Prefer a loopback OpenAI-compatible adapter when the required UX is ordinary model selection and native agent-protocol semantics are not required because the smaller boundary is easier to verify and roll back.
- Keep subscription or CLI authentication inside the official client; do not repoint a direct API provider at a different service host or extract browser/session credentials because host and entitlement are separate.
- Bind adapters to loopback, remove conflicting API-key environment variables only in the child process, expose health/models/chat endpoints, and use bounded long timeouts because provider bridges are credential-bearing subprocesses.
- Verify the final Hermes invocation, exact model catalog entry, response translation, restart behavior, and picker visibility because protocol initialization alone does not prove usable provider integration.
- Generalize provider dispatch through a table when adding a second subprocess provider; do not copy provider-specific branches or use broad replacements because duplicated fallbacks create unreachable paths.
- Isolate provider work in a worktree when the main repository is dirty and preserve local changes because provider integration must not overwrite unrelated edits.

## Multimodal and vision benchmarks

- Label benchmark snapshots with their source generation and date, and re-fetch before calling values current because benchmark cohorts and task sets change.
- Compare models only on matched task definitions, cohorts, and evaluation generations because legacy and current scores are not clean head-to-head evidence.
- Separate vision, OCR, GUI grounding, multimodal reasoning, latency, and cost claims because a general model index does not establish screen-control ability.
- Run deterministic end-to-end canaries through the actual Hermes route with explicit provider, model, image, and semantic-output checks because provider CLI timings omit runtime and transport overhead.
- Report the acceptance protocol and failure boundary alongside scores because a synthetic image can validate routing without proving robust real-world grounding.
