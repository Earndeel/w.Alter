---
name: agent-loop-prevention
category: software-development
description: Stop and diagnose when the same tool errors repeatedly — 3-strike rule, error-class triage, and recovery patterns to avoid burning a session on identical failures.
---

# Agent Loop Prevention

When the same tool returns the same error class three times in a turn, **stop and diagnose**. Continuing past that point has been observed to produce 60+ identical failures in a single session, polluting context, burning tokens, and frustrating the user.

This skill applies to ANY repeated tool failure, not just one tool. The pattern is universal: misread error → retry → retry → retry → loop.

## The 3-Strike Rule

Stop conditions (any one fires):

- Same tool name + same error category 3× in the current turn.
- The agent runtime surfaces an explicit loop warning (e.g. `same_tool_failure_warning; count=3`).
- The error payload contains a config-or-credential phrase: `not configured`, `unauthorized`, `401`, `422`, `missing direct config`, `missing tool-gateway auth`, `subscription token invalid`, `API key not set`.
- The error contains a path-not-found or permission phrase that won't change with retries: `no such file`, `permission denied`, `command not found`.

If any of these fire, the next action is **diagnosis**, not retry.

## Error-Class Triage

Classify the error before deciding what to do next. Retries only fix one class.

| Class | Examples | Will retry help? | Right action |
|---|---|---|---|
| Transient network | timeout, connection reset, 502/503/504 | Yes, with backoff | Retry with delay, up to 3× total |
| Rate limit | 429, `rate exceeded` | Yes, after wait | Wait the indicated period, retry once |
| Config missing | `not configured`, empty backend setting | **No** | Inspect config, fix or surface to user |
| Credential missing | `API_KEY not set`, env var absent | **No** | Look up credential, surface to user |
| Credential invalid | 401, 403, 422 token-invalid | **No** | Compare to authoritative source (vault, dashboard), surface to user if revoked |
| Path / file missing | `no such file`, `not found` | **No** | Check actual filesystem, adjust path or surface gap |
| Logic / argument error | bad input, schema mismatch | **No** | Re-read tool schema, fix arguments |

Retrying on a non-transient class is the loop trap.

## Diagnostic Sequence (instead of a 4th retry)

1. **Read the actual error string**, not the tool name. The payload tells you the class.
2. **Check the agent runtime config** for the relevant capability. An empty string in a backend field means "fall through to default," which is rarely what the user wants.
3. **Inspect credentials** wherever they live (env file, secret manager, vault). Look for: missing entirely, placeholder values, obvious length mismatch with the expected key format.
4. **Cross-check against an authoritative source** (vault, provider dashboard). If identical and still rejected upstream, the credential is revoked — that's a user action, not an agent retry.
5. **Report to the user**: failing tool, precise error string, the config or credential at fault, the proposed fix. Then wait.

## Recovery Patterns

- **Switch path, not retry**: if `tool A` fails on config-missing, ask whether `tool B` (different backend, different transport) is available, rather than calling `tool A` again with the same arguments.
- **One probe is enough**: a single carefully chosen tool call to confirm "yes, the credential is indeed missing/invalid" is worth more than five retries hoping the world changed.
- **Don't fabricate**: if no real path exists right now, surface the blocker. Never substitute plausible-looking output for results you couldn't actually produce.
- **Preserve user processes**: don't kill long-running user processes (TUI, daemons) as part of recovery without explicit permission, even if a restart would pick up new config.

## Common Loop Anti-Patterns

- Calling the same search/web tool 20+ times while the underlying provider is misconfigured — the error message is the same every time, the fix is one config change.
- Calling `memory replace` repeatedly with a search string that doesn't match any entry — list entries once, then act with a real anchor.
- Calling a tool with the same broken arguments because the previous error didn't suggest different ones — re-read the schema or the prior payload.
- Calling an editor/patch tool with `old_string` that doesn't exist in the file — view the file once, copy the real text, then patch.
- **Empty-result scatter-bomb**: firing 5 different tools (`session_search`, `web_search`, `tool_search`, `hindsight_recall`, `hindsight_reflect`) with the same garbage query. Different tool names ≠ different approach. If multiple tool types all return empty for the same query, the problem is the *query* or the *approach*, not the tool. Stop after 2 empty results across different tools and reconsider what you're actually looking for.
- **Using skill documentation text as tool arguments**: fragments of SKILL.md instructions (e.g. `a pet: \\`hermes pets list <query>\\` and note its \\`slug\\``) getting passed as search queries to unrelated tools. Skill docs describe what the *agent* should do, not what to feed as input to `web_search` or `hindsight_recall`.
- **Redundant context re-querying**: Launching search/recall tools for data that is already available in the current session context. If the user asks about a status, fact, or configuration that has already been covered, succeed immediately by extracting the answer from the turn history or prior tool results. Do not call `session_search`, `web_search`, `tool_search`, `hindsight_recall`, or `hindsight_reflect` with the same query after they have already been executed in the same session. The system warning `idempotent_no_progress_warning` indicates this exact anti-pattern.

## Logging Where the Loop Lives

Most agent runtimes log loop detections to an `errors` log. Knowing the exact phrase your runtime uses for the warning lets you grep for past incidents and confirm whether a current session is repeating a known pattern. Examples seen in the wild include `same_tool_failure_warning`, `tool loop detected`, `repeated failure`.

## When Setup IS the Problem

If the loop is caused by missing setup (uninstalled package, unconfigured credential, broken config file), the **fix goes into the setup or troubleshooting skill for that subsystem**, not here. This skill is about *recognizing and breaking the loop*; the per-subsystem skill carries the actual repair recipe.
