# Archived conversational-workflow routing

Confirm the archive root with `skill_view(name='.archive/<name>')` and use its original relative support paths. The archive is historical; verify deployed contracts before changing or claiming state.

- `.archive/conversational-workflow-orchestration/SKILL.md` — validation-first state machine and execution gates.
  - `.archive/conversational-workflow-orchestration/references/scena-telegram-pattern.md` — Telegram/D1 intake and runner rules.
  - `.archive/conversational-workflow-orchestration/references/payload-forensics-stale-runs.md` — stale-run and payload consistency forensics.
  - `.archive/conversational-workflow-orchestration/references/composable-skills-and-gates.md` — skills-first workflow and durable revision gates.
  - `.archive/conversational-workflow-orchestration/references/tool-call-fault-containment.md` — parse-once, per-call error isolation, and retry safety.
- `.archive/conversational-intake-orchestration/SKILL.md` — natural dialogue inside deterministic intake.
  - `.archive/conversational-intake-orchestration/references/scena-telegram-guided-intake.md` — objection/question routing and regression shape.
  - `.archive/conversational-intake-orchestration/references/client-facing-response-style.md` — concise visible response contract.
  - `.archive/conversational-intake-orchestration/references/openrouter-model-reasoning-contract.md` — model-role and reasoning controls.
- `.archive/multimodal-conversational-intake/SKILL.md` — text/image/voice collection and planner handoff.
  - `.archive/multimodal-conversational-intake/references/scena-luna-sol-july-2026.md` — multimodal routing and planner sequence.
  - `.archive/multimodal-conversational-intake/references/stateful-intake-handoff-harness.md` — durable snapshot and deterministic readiness gate.
