---
name: fable-planner-executor-pipeline
description: Run and troubleshoot a Fable 5 planner → configurable Hermes executor pipeline, including model value routing, explicit query-mode tool calling, usage accounting, failure handling, and evidence-backed replanning.
---

# Fable 5 Planner / Configurable Hermes Executor

## Trigger

Load this skill when operating or debugging `fable_pipeline.py`, the Fable 5 → pxpipe/Kie.ai planner, an isolated Hermes executor, executor-model selection, `EXECUTION_REPORT` parsing, usage files, or replan behavior.

## Reference implementation

- Launcher: `/root/.hermes/skills/devops/pxpipe-planning-proxy/scripts/fable_pipeline.py`
- Tests: `/root/.hermes/skills/devops/pxpipe-planning-proxy/tests/test_fable_pipeline.py`
- Planner endpoint: `127.0.0.1:47822`
- Planner model: `claude-fable-5`
- Executor: configurable model/provider pair; never assume that the initially tested model is the permanent default
- Verified baseline executor: `claude-sonnet-5` via `custom:kie-pxpipe`
- Current value candidate: `deepseek/deepseek-v4-pro` with maximum reasoning via OpenRouter; benchmark evidence is not a substitute for a pipeline A/B test
- Plan contract: `PLAN_CONTRACT`
- Executor report contract: `EXECUTION_REPORT`

## Full run

```bash
cd /root/.hermes/skills/devops/pxpipe-planning-proxy
python3 scripts/fable_pipeline.py run \
  --task-file /tmp/task.txt \
  --workdir /tmp/fable-work \
  --plan-output /tmp/fable-plan.json \
  --report /tmp/fable-report.json \
  --usage-file /tmp/fable-usage.json
```

The runner validates the plan, executes it through isolated Hermes, and allows one evidence-backed replan by default.

## Separate planning and execution

```bash
cd /root/.hermes/skills/devops/pxpipe-planning-proxy
python3 scripts/fable_pipeline.py plan \
  --task-file /tmp/task.txt \
  --output /tmp/fable-plan.json

python3 scripts/fable_pipeline.py execute \
  --plan /tmp/fable-plan.json \
  --workdir /tmp/fable-work \
  --report /tmp/fable-report.json \
  --usage-file /tmp/fable-usage.json
```

## Execution guarantees

1. Execute with explicit Hermes query mode: `hermes chat -Q -q`.
2. Keep `-q`; it is the explicit tool-calling execution path. `-Q` only suppresses the echoed prompt and tool previews.
3. Pin the exact selected model/provider for each run and record them in usage output; never substitute silently. Model selection is a routing decision, not an architectural constant.
4. Apply the plan's `execution.max_turns` through both `--max-turns` and the isolated temporary `HERMES_HOME` configuration.
5. Pass the Kie credential only to the child executor environment; never write it into reports or documentation.
6. Stop only the proxy process started by this launcher. Never use broad process-killing commands.
7. Parse the last JSON object matching `report_type: EXECUTION_REPORT`; an echoed schema must never be accepted as the final report.

## Executor model routing

The planner/executor split lowers the executor's planning burden, so a value model can be sufficient for well-scoped plans even when its long-horizon agentic benchmark is below the premium model.

1. Verify the exact model ID and live provider price before configuration.
2. Compare **cost per task**, GDPval-AA, TerminalBench, coding, tool calling, and structured-output support; blended token price alone is not enough.
3. A strong budget candidate such as DeepSeek V4 Pro Max may be the default only after a real A/B on this pipeline: identical plans, toolsets, turn limits, success criteria, artifact hashes, and failure injection.
4. Keep the verified premium model as escalation when the budget executor returns an invalid report, repeatedly fails tools, cannot recover after replan, or fails artifact verification.
5. Do not treat a benchmark recommendation as a completed configuration change. Update the launcher only after the A/B proves the intended success-rate/cost trade-off.

See the `model-value-analysis` skill and its `references/deepseek-v4-pro-vs-sonnet-5-july-2026.md` snapshot for the dated evidence; keep benchmark research under that class-level umbrella rather than duplicating it here.

## Usage accounting

`hermes chat` does not populate a file from the global `--usage-file` flag. The launcher therefore reads the latest executor session from the isolated `HERMES_HOME/state.db` after `chat` exits and writes:

- requested usage path, for example `/tmp/fable-usage.json`;
- raw CLI output beside it, for example `/tmp/fable-usage.raw.txt`.

For a custom provider, token counts and API-call counts are available, but cost remains `cost_status: unknown` unless Hermes has explicit pricing.

On replan, the first attempt is preserved as:

- `report.replan-1.json`;
- `usage.attempt-1.json`;
- `usage.attempt-1.raw.txt`.

The final successful attempt remains at the requested report and usage paths.

## Replan workflow

1. Execute the validated initial plan.
2. Accept a replan only when the report is `blocked`, `replan_needed` is true, and real evidence identifies a major strategic blocker.
3. Preserve the initial report and usage files before replanning.
4. Send the previous plan plus its execution report to Fable 5.
5. Validate the replacement plan before execution.
6. Execute once more and return exit 0 only when the final report status is `completed`.

## Verification

Run the unit suite:

```bash
cd /root/.hermes/skills/devops/pxpipe-planning-proxy
python3 -m unittest discover -s tests -v
```

For an end-to-end test, verify all of the following from real artifacts:

- command returns exit 0;
- final JSON has `report_type: EXECUTION_REPORT` and `status: completed`;
- requested deliverables exist and pass byte/hash checks;
- usage JSON contains the expected model, provider, session ID, token counts, and API-call count;
- a forced major blocker preserves `report.replan-1.json` and ends with `replans: 1`.

## Verified baseline — 2026-07-10

- Unit suite: exit 0.
- Direct executor run: `completed`; output 17 bytes; SHA-256 `716ee5ad9c5ba48b6526c3b8fc11983f9696e0bcacc7b21b979f23d5cb07f609`.
- Full planner → source disappearance → blocked executor → replan → executor cycle: exit 0, `replans: 1`, final `completed`, same verified 17-byte output and SHA-256.
- Final executor usage observed: 41,077 tokens across 8 API calls, model `claude-sonnet-5`, provider `custom`; cost unknown because no tariff was exposed.

## Pitfalls

- Do not put `--usage-file` before `chat` and assume chat populated it; that global flag is for one-shot mode, not `hermes chat`.
- Without `-Q`, query text and schema examples may be echoed before the final JSON. Keep robust matching even when quiet mode is enabled.
- Executor cleanup commands can hit approval gates. Finalize harmless temporary-file cleanup from the orchestrator and verify absence explicitly.
- Do not mark a run successful merely because the subprocess exited 0; validate the JSON contract and the requested deliverables.
- A `completed` report may still mention cleanup deviations. Inspect `errors` and evidence, then correct and verify them before reporting completion.
