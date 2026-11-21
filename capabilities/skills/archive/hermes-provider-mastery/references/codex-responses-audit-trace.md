# Codex Responses Provider Audit Trace

Systematic methodology for auditing any provider's Responses API integration
end-to-end in the Hermes codebase. Derived from the Kie GPT / gpt-5-6-sol audit
(2026-07-13) but applicable to any `api_mode="codex_responses"` provider.

## When to Use

- Auditing a new or existing `codex_responses` provider
- Debugging 400/403 errors from the Responses API
- Verifying payload correctness after Hermes upgrade
- Tracing the full request path before a provider ships

## Audit Steps (in order)

### 1. Config Resolution

Start from `config.yaml` → trace how the provider is resolved:

- `plugins/model-providers/<slug>/__init__.py` → provider profile (base_url, api_mode, models)
- `agent/agent_init.py:850-1035` → `_init_new_client_with_config()` → api_mode determination, effective_base, client kwargs

### 2. Runtime Resolution

- `hermes_cli/runtime_provider.py:280-290` → `_resolve_runtime_from_provider()` — but for `codex_responses`, `api_mode` is already set via `_init_new_client_with_config`, so this is bypassed
- `agent/auxiliary_client.py:4371-4770` → `resolve_provider_client()` — routes to `"openai-codex"` for Responses-compatible providers

### 3. Client Construction (Two Paths)

**Path 1 — Main agent loop:**
- `agent/agent_init.py:910-935` → calls `agent/agent_runtime_helpers.py:1632-1788` → `create_openai_client()`
- `agent/transports/codex.py:64-185` → `build_kwargs()` — appends `/responses` suffix to base_url

**Path 2 — Auxiliary/tools:**
- `agent/auxiliary_client.py:2434-2501` → `_build_codex_client()` → creates `CodexAuxiliaryClient` wrapper
- `agent/auxiliary_client.py:1164-1350` → `CodexAuxiliaryClient` — chat.completions → responses translation
- `agent/auxiliary_client.py:840-1039` → `_CodexCompletionsAdapter` — format conversion layer

### 4. Headers & URL

- `run_agent.py:4370-4454` → `_apply_client_headers_for_base_url()` — per-host User-Agent injection
- Key check for Kie: `api.kie.ai` host → Chrome 124 Linux User-Agent required
- Final URL: `base_url` + `"/responses"` (e.g., `https://api.kie.ai/codex/v1/responses`)

### 5. Payload Construction

- `agent/codex_runtime.py:46-92` → `run_codex_stream()` — assembles instructions, tools, input
- `agent/codex_responses_adapter.py:306-550` → `_chat_messages_to_responses_input()` — chat→responses conversion, encrypted reasoning replay, cross-issuer guard
- `agent/codex_responses_adapter.py:79-127` → `_chat_content_to_responses_parts()` — multimodal content conversion
- Tools defined in `codex_runtime.py:46-72` → custom_tool definitions (mcp__*, read, write, edit, run_shell_command, spawn_subagent)

### 6. SSE Stream Processing

- `agent/codex_runtime.py:88-370` → event iteration loop
  - `response.output_text.delta` → text accumulation
  - `response.reasoning_text.delta` → reasoning accumulation
  - `response.reasoning_summary_text.delta` → summary accumulation
  - `response.function_call_arguments.delta` → tool call construction
  - `response.completed` / `response.failed` → finalization

### 7. Response Normalization

- `agent/codex_responses_adapter.py:1071-1353` → `_normalize_codex_response()`
  - Phase handling: `commentary`/`analysis` → reasoning channel, `final_answer` → content
  - Server-side tool calls (web_search_call, code_interpreter_call, etc.) excluded from incomplete detection
  - `encrypted_content` preservation with `_issuer_kind` stamp
  - Transient item filtering (`rs_tmp_*` IDs)
- `run_agent.py:4138-4338` → `_run_codex_stream()` wrapper in AIAgent

### 8. Git Diff Check

```bash
cd ~/.hermes/hermes-agent && git diff HEAD
```

Always verify the working tree is clean before concluding an audit — local patches may alter behavior.

## Key File Map

| File | Lines | Role |
|------|-------|------|
| `agent/agent_init.py` | 850-1035 | Provider → api_mode → client resolution |
| `agent/transports/codex.py` | 1-450 | URL suffix, build_kwargs |
| `agent/codex_runtime.py` | 1-1150 | SSE loop, stream processing |
| `agent/codex_responses_adapter.py` | 1-1353 | Chat→Responses conversion, normalization |
| `agent/auxiliary_client.py` | 840-1350 | _CodexCompletionsAdapter, CodexAuxiliaryClient |
| `agent/auxiliary_client.py` | 2434-2501 | _build_codex_client |
| `agent/auxiliary_client.py` | 4371-4770 | resolve_provider_client |
| `agent/agent_runtime_helpers.py` | 1632-1788 | create_openai_client |
| `run_agent.py` | 3992-4070 | _replace_primary_openai_client |
| `run_agent.py` | 4138-4338 | _run_codex_stream wrapper |
| `run_agent.py` | 4370-4454 | _apply_client_headers_for_base_url |
| `plugins/model-providers/<slug>/__init__.py` | 1-50 | Provider profile |

## Common Risks (Provider-Agnostic)

1. **403 if User-Agent missing**: Some providers (Kie) block OpenAI SDK User-Agent. Check `_apply_client_headers_for_base_url()` for host-specific header injection.
2. **400 `invalid_encrypted_content`**: Cross-issuer reasoning replay. Check `_issuer_kind` stamping and the per-item filter in `_chat_messages_to_responses_input`.
3. **Empty output with output_text**: Fallback synthesizes an item; if both are absent → RuntimeError with no retry.
4. **No payload logging**: No point captures the full request body. Inject debug logging at `codex_runtime.py:88`.
5. **Hardcoded `tool_choice="auto"`**: Not configurable per-provider.

## Debug Payload Capture Points

Inject logging at these exact locations:
- `codex_runtime.py:88` — before `self._client.responses.create()`
- `codex_responses_adapter.py:306` — entry/exit of message conversion
- `transports/codex.py:140` — after `build_kwargs()`, full headers
