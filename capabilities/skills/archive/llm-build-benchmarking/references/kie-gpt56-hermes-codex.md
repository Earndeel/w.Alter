# Kie GPT-5.6 via isolated Hermes profiles and Codex CLI

## Hermes profile routing

A cloned profile may retain top-level `model.base_url`, `model.api_mode`, and `model.transport` from its source. Enabling `kie-gpt-provider` and passing `--provider kie-gpt` is insufficient if those fields still point elsewhere.

Set each benchmark profile explicitly:

```bash
hermes -p <profile> config set model.provider kie-gpt
hermes -p <profile> config set model.default <gpt-5-6-model>
hermes -p <profile> config set model.base_url https://api.kie.ai/codex/v1
hermes -p <profile> config set model.api_mode codex_responses
hermes -p <profile> config set model.transport codex_responses
hermes -p <profile> config set agent.reasoning_effort <level>
hermes -p <profile> plugins enable kie-gpt-provider --no-allow-tool-override
```

Before the real run, issue a tiny exact-response smoke test. Query the profile's session database and require:

- `model` equals the candidate model;
- `billing_provider` equals `kie-gpt`;
- `billing_base_url` equals `https://api.kie.ai/codex/v1`.

Terminal provider labels alone are not evidence.

## Direct Codex CLI isolation harness

Use this to distinguish Hermes orchestration failures from model/provider failures. Run inside a clean Git repository and load the key without printing it:

```bash
set -a
. /path/to/profile/.env
set +a

codex exec \
  --dangerously-bypass-approvals-and-sandbox \
  --ephemeral --json \
  -m gpt-5-6-luna \
  -c 'model_provider="kie"' \
  -c 'model_reasoning_effort="high"' \
  -c 'model_providers.kie={ name="Kie GPT", base_url="https://api.kie.ai/codex/v1", env_key="KIE_API_KEY", wire_api="responses", requires_openai_auth=false, http_headers={ "User-Agent"="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36" }, request_max_retries=2, stream_max_retries=5, stream_idle_timeout_ms=900000 }' \
  '<exact benchmark prompt>'
```

The browser-like User-Agent is part of the Kie transport contract. The extended stream idle timeout matters for high-reasoning generations that may remain silent for long periods.

## Fair reruns

- Delete only generated artifacts inside the candidate workspace.
- Prove `git status --porcelain` is empty before launch.
- Preserve the exact original prompt.
- Keep the original model and reasoning effort.
- Clearly label a direct Codex rerun as a different harness; do not merge its timing into the Hermes run.

## Interpretation

A short smoke test can succeed while a long tool-generating stream later stalls. If a run aborts after partial writes, inspect runtime completeness: for example, an `index.html` referencing a missing `game.js` is a DNF even if HTML/CSS are polished.

Keep the failed Hermes run and a successful Codex rerun as two distinct observations:

- the first measures end-to-end reliability through Hermes;
- the second isolates whether the model can complete through the Kie Responses-compatible Codex harness;
- success on rerun does not erase the original DNF or make token/time figures cross-harness comparable.

For web-game or visual builds, independently serve each artifact, click through the start flow, inspect browser/runtime errors, and capture a screenshot. A rising score or changing runtime state is stronger gameplay evidence than a static canvas image. When the user wants hands-on comparison on a Mac, copy each verified static artifact into separate directories, serve them on distinct loopback ports, verify HTTP 200 locally on the Mac, then open both raw loopback URLs in Brave.

## GPT-5.6 cost reporting note

Kie published list rates must be fetched again at report time. In the July 2026 comparison, public rates were Luna `$1/$6` and Sol `$5/$30` per 1M input/output tokens. Codex reports cached input separately, but do not assume Kie applies OpenAI's cache discount unless Kie's billing documentation confirms it. Show conservative and cache-adjusted estimates separately.