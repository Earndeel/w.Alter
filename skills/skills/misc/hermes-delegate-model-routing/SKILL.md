---
name: hermes-delegate-model-routing
category: devops
description: "Route subagents to specific models from the orchestrator. Documents the runtime lock in delegate_task, three workarounds (named routes, free params, profiles), and verification methods."
tags: [hermes, delegation, routing, subagents, models]
---

# Dynamic Model Routing for Subagents

How an orchestrator can route a subagent to a specific model at call time.

## Core Finding (Hermes v0.16.0)

The orchestrator cannot pass model or provider to delegate_task at call time. Hard lock, by design.

Evidence from tools/delegate_tool.py:
- DELEGATE_TASK_SCHEMA (line ~2945-3080): properties are goal, context, toolsets, tasks, role, background, acp_command, acp_args. No model.
- delegate_task() signature (line ~2044-2054): no model parameter.
- Handler lambda args: delegate_task(**args) (line ~3090): does not forward args.get("model").
- max_iterations is explicitly authoritative (line ~2118-2128): model-supplied values are logged and dropped.

Passing {"model": "x", "provider": "y"} in args is silently ignored. The subagent runs on whatever delegation.model / delegation.provider are set in the global yaml at session start.

## Three Real Workarounds

| Workaround | Effort | Flexibility | Audit |
|---|---|---|---|
| A. Named routes (route="code") | ~30 LOC | Medium | High |
| B. Free model= / provider= | ~50 LOC | High | Low |
| C. Pre-configured profiles | 0 LOC | High (N profiles) | High |

Recommended: Workaround A. Keeps a routing table in yaml (auditable, version-controlled), exposes a single route= parameter (predictable), matches existing _resolve_delegation_credentials() pattern.

Workaround C is best when you want isolated memory/skills per model — heavier setup, not callable from delegate_task.

## Workaround A — Named Routes

### Routing table example

```yaml
delegation:
  routes:
    cheap:    {model: mimo-v2.5-flash,         provider: xiaomi}
    default:  {model: mimo-v2.5-pro,           provider: xiaomi}
    deep:     {model: deepseek/deepseek-v4-pro, provider: openrouter}
    code:     {model: claude-opus-4-7,         provider: kie-claude}
    research: {model: kimi-k2.6,               provider: opencode-go}
```

### Patch sketch (delegate_tool.py)

```python
# 1. Add to DELEGATE_TASK_SCHEMA["properties"]:
"route": {
    "type": "string",
    "description": "Named route from delegation.routes. Resolves to (model, provider) at call time. Default: uses delegation.model / delegation.provider."
}

# 2. Add to delegate_task() signature:
def delegate_task(goal=None, context=None, toolsets=None, tasks=None,
                  max_iterations=None, acp_command=None, acp_args=None,
                  role=None, background=None, parent_agent=None,
                  route=None):

# 3. After _resolve_delegation_credentials() (~line 2136):
if route:
    routes = cfg.get("routes", {}) or {}
    if route not in routes:
        return tool_error(
            f"route='{route}' not declared in delegation.routes. "
            f"Available: {list(routes.keys())}"
        )
    r = routes[route]
    creds["model"] = r.get("model") or creds.get("model")
    creds["provider"] = r.get("provider") or creds.get("provider")
    logger.info(
        f"delegate_task route={route} resolved -> model={creds['model']} "
        f"provider={creds['provider']} base_url={creds.get('base_url')}"
    )
```

### Orchestrator call

```python
delegate_task(goal="fix webhook race", route="code")     # -> claude-opus-4-7
delegate_task(goal="rename files", route="cheap")         # -> mimo-v2.5-flash
delegate_task(goal="research 10 papers", route="research") # -> kimi-k2.6
```

No route= -> falls back to current delegation.model / delegation.provider (backward compatible).

## Verifying Routing Works

Three layers of evidence:

1. **Logic test in pure Python (fast, no daemon restart).** Before the user restarts the gateway, import `delegate_task` and exercise the route resolution function with a fake `cfg` and a mocked `parent_agent`. The patched `_resolve_delegation_credentials` is reachable via `from tools.delegate_tool import _resolve_delegation_credentials` (after the patch is in place). For the route name validation specifically, write a 50-line test that calls the patched function with route="code" / route="unknown" / route=None and asserts the resolved model/provider and the error string. If the test fails, the patch is broken — fix it before asking the user to restart. If it passes, the routing logic is sound and only runtime wiring remains to verify.
2. **Log the resolution.** The patch above adds `logger.info(...)`. Without it, a typo in yaml looks like silent fallback. After the user restarts, run a `delegate_task` call and grep the log for `route=... resolved -> model=... provider=...`.
3. **A/B on real tasks.** Run the same goal on 2 routes, diff outputs. If `cheap` and `code` produce the same answer, you're overpaying for `code`. Choose tasks that have 2-3 distinct sub-competencies (e.g. read+refactor+find-bug) — easier to spot a difference than a single 1-shot prompt.

### Do NOT use hermes chat --cli for one-shot tests

hermes chat --cli spawns the interactive TUI loop. In a non-TTY context it blocks on _interrupt_queue.get(timeout=0.1) and never sends the API request. The process hangs until the parent timeout kills it (180s default). Confirmed in test: hermes chat -m claude-opus-4-8 --provider kie --cli -q "..." < /dev/null ran 180s, then timeout killed it with EXIT=124. No API request was ever sent.

Use the runtime provider directly in Python via execute_code, or call delegate_task from inside an active session.

### End-to-end latency canary for a Hermes provider route

When measuring the model/provider route actually used by Hermes, use the Hermes one-shot runtime rather than the standalone provider CLI. For OpenAI Codex OAuth, the two paths have separate credential stores and defaults:

```bash
hermes chat -q 'Reply exactly SPEED_OK. Do not use tools.' \
  -m gpt-5.6-luna --provider openai-codex -Q --ignore-rules
```

For a vision route, attach a known test image and require exact markers that prove the image was read:

```bash
hermes chat -q 'Inspect the attached image. Reply exactly: VISION_OK <known markers>.' \
  --image /tmp/known-screen.png -m gpt-5.6-luna \
  --provider openai-codex -Q --ignore-rules
```

Run three identical canaries and measure wall time around each subprocess. Report median/min/max and verify the marker in the final response. Label the result end-to-end: it includes Hermes startup, authentication, transport, and model response, not pure inference. `--ignore-rules` isolates user rules/skills while retaining provider configuration and auth; do not use `hermes chat --cli` for this one-shot measurement. A `401` from bare `codex exec` is an authentication-path mismatch, not a latency result.

### Do NOT curl-test providers behind Cloudflare directly

Direct curl to https://api.kie.ai/claude/v1/messages (or similar) returns HTTP 403 error code 1010 — Cloudflare blocks browser-signature-less requests from server IPs. The Hermes runtime uses a different transport fingerprint and gets through.

### Kie.ai protocol gotchas (validated 2026-06-16 with real call)

- **Kie.ai uses Anthropic Messages protocol, NOT OpenAI Chat Completions.** The endpoint is `https://api.kie.ai/claude/v1/messages`, not `/v1/chat/completions`. Confirmed: Anthropic-format request → HTTP 200, OpenAI-format request → HTTP 404.
- **Config.yaml `providers.kie.api_mode: chat_completions` is WRONG.** It should be `anthropic_messages`. Until you fix it, the runtime sends OpenAI-format requests to Kie.ai, gets 404, and silently falls back to the parent model. Subagent "routed to kie" was never actually running on Kie.ai.
- **Headers required**: `Authorization: Bearer *** AND `anthropic-version: 2023-06-01`. NOT `x-api-key` (that's raw Anthropic, Kie.ai uses Bearer).
- **Response model field matches request** (no silent swap). If you ask for `claude-opus-4-8`, the `body.model` field is `claude-opus-4-8`. Useful for verifying routing end-to-end.
- **Response `usage` includes `cache_creation` and `cache_read_input_tokens`** — Kie.ai supports prompt caching with Anthropic-style ephemeral 1h/5m TTLs.
- **Latency baseline** (claude-opus-4-8, 26 input + 28 output tokens): ~8.67s. Cost: 0.07 credits.
- **Cloudflare blocks raw urllib** with HTTP 403 error code 1010. Use a browser-like User-Agent header OR route through the Hermes runtime.
- **Fix checklist when subagent "on kie" silently uses parent model**: (1) set `api_mode: anthropic_messages` in `providers.kie`, (2) `/reset` to invalidate session cache, (3) send a 1-token canary to verify the model field in the response.

See skill `kie-ai-api-direct` for the full validated Python/curl recipes. See `references/kie-ai-endpoint-validated.md` in this skill for the end-to-end fix checklist (config edit + restart scope + verification recipe).

## Budget Guard (Optional)

Add per-session cost limits per route:

```yaml
delegation:
  routes: { ... }
  budget_per_session:
    code:  0.05
    deep:  0.02
```

In the patch, check accumulated cost via a session-scoped counter. If over budget, return a tool_error with "Falling back to route='default'".

## Core Patches Do NOT Survive `hermes update`

Confirmed 2026-07-04: a routing patch applied directly to `agent/agent_runtime_helpers.py` (forcing execution model) was silently erased by a later `hermes update` — the updater rewrites core source files. Any behavior change implemented as a source patch to `/root/.hermes/hermes-agent/` is temporary.

Rule: for durable routing/cost behavior, use ONLY config-level mechanisms:
- `delegation.model` / `delegation.provider` in config.yaml (survives updates) — subagents via delegate_task run on the cheap executor while the main model stays the orchestrator.
- Named routes (Workaround A) must be re-applied after every update if implemented as a source patch — prefer upstreaming or a post-update re-patch script if you keep it.

Verification after any `hermes update`: grep the patched files for your marker strings before assuming routing is still active. Silent fallback to the parent model is the failure mode.

## Orchestrator/Executor Cost Pattern (config-only, update-proof)

Cheapest durable setup: expensive model as main (strategy, synthesis), cheap executor via `delegation.model` (e.g. deepseek/deepseek-v4-pro on openrouter). No source patch needed. The discipline that makes it pay: any execution-heavy task (>3-4 tool calls: code, scraping, batch processing) goes through delegate_task with a detailed brief; the orchestrator only plans and synthesizes. If the orchestrator does the execution inline, the config routing saves nothing.

## Cache Caveat

delegate_task caches `delegation.model` / `delegation.provider` at session start. Changing the `routes` block mid-session has zero effect until `/reset`. Same pattern as existing `delegation.*` fields.

**Two invalidation scopes:**
- **Source patch (delegate_tool.py)**: takes effect on the next Python process import. Pure-Python logic tests (like the one in the "Verifying Routing Works" section) can exercise the new code WITHOUT a daemon restart because they reimport the module. But the running gateway/TUI/cron still uses the OLD source — restart the gateway to pick up the patch.
- **Config edit (config.yaml)**: takes effect on the next `_load_config()` call. The gateway caches `CLI_CONFIG` at startup, so an edit to `config.yaml` requires `/reset` (TUI session) or `kill + restart` (gateway/cron).

**Minimum restart cost to test routing end-to-end**: edit config.yaml (add `routes:` + fix `api_mode` for kie) → `/reset` in the TUI → call `delegate_task(route="code")` → check log for `route='code' resolved → model=claude-opus-4-8 provider=kie`. The TUI session is preserved across `/reset`; only the model cache and CLI_CONFIG are dropped.

## Code-Verified Subagent Routing Architecture

The former `subagent-model-routing-architecture` skill is absorbed as `references/subagent-model-routing-architecture.md`. Use it when you need the source-level explanation of why delegate subagents inherit the parent transport/model route and why per-call model parameters are ignored.

Class-level rules:
- Verify routing claims against `tools/delegate_tool.py`, not assumptions from the tool schema shown to the model.
- Distinguish profile-level routing, ACP command delegation, and in-process `delegate_task`; they have different isolation and credential semantics.
- When building a workaround, test the resolver in pure Python first, then verify runtime logs after gateway/session reset.

## See Also

- Skill hermes-multi-agent-profiles — overall multi-agent architecture, profiles
- Skill hermes-provider-mastery — provider config patterns
