# Verified Wire Payload Assembly Map (api_kwargs lifecycle)

Verified by direct source inspection (read-only audit) on `main @ c0106e50e7`.
Working tree was dirty; the cited files below (`run_agent.py`, `agent/transports/*`,
`hermes_cli/middleware.py`) were clean at audit time, so line numbers are reliable
for them. `agent/chat_completion_helpers.py` / `agent/conversation_loop.py` were dirty
— re-verify line numbers for those if they drift.

Purpose: when diagnosing provider 400s, adding an instrumentation/dump, or auditing
context bloat, this is the path from the conversation loop to the bytes actually sent.

## 1. Single assembly chokepoint: `build_api_kwargs`

- Called from turn loop: `agent/conversation_loop.py:2516` (or `:2518` when a
  toolset override is passed).
- Forwarder: `run_agent.py:7129-7132` (`agent._build_api_kwargs`).
- The function: `agent/chat_completion_helpers.py:1330` — ONE function returns the
  final provider kwargs dict for every `api_mode`. This is the highest-value place to
  trace any payload question.

## 2. Per-`api_mode` branches inside build_api_kwargs

| api_mode | branch | transport build_kwargs | wire adapter |
|---|---|---|---|
| `anthropic_messages` | 1335-1361 | `agent/transports/anthropic.py:41-78` | `agent/anthropic_adapter.py:2849` (returns `kwargs` at `:3075`); Nous Portal extra-body merge `chat_completion_helpers.py:199` |
| `bedrock_converse` | 1365-1376 | `agent/transports/bedrock.py:32-65` — injects sentinels `__bedrock_converse__`/`__bedrock_region__` at `:63-64` | `agent/bedrock_adapter.py:1018` (converse-format kwargs: `modelId`, `messages`, `inferenceConfig`, `system`, `toolConfig`, `guardrailConfig`) |
| `codex_responses` | 1378-1463 | `agent/transports/codex.py:223` — extracts `instructions` from messages[0], clamps reasoning effort, xAI web-search swap, GitHub/Copilot extras | native compaction resolved via `agent/native_compaction.py`; input/tools conversion in `agent/codex_responses_adapter.py:341` (`_responses_tools`) / `:410` (`_chat_messages_to_responses_input`) |
| `chat_completions` (default) | 1537-1567 profile path; 1569-1614 legacy path | `agent/transports/chat_completions.py` `_build_kwargs_from_profile` `:599` (return `:747`) or `build_kwargs` `:356` (return `:597`); prompt cache key `_add_prompt_cache_key` `:44` | profile extras via `providers/` (`build_api_kwargs_extras`, `build_extra_body`) |

Pitfalls encoded in build_api_kwargs worth knowing:
- xAI Responses rejects `pattern`/`format`/slash-enum in tool schemas — sanitized on a
  DEEPCOPY of `tools_for_api` (else the first xAI request permanently strips
  `agent.tools`, #27907).
- Native Gemini (generativelanguage) prunes `extra_body` to only thinking keys
  (`chat_completions.py:726-735`) because it rejects unknown OpenAI-style fields.

## 3. Post-build mutation before dispatch (all in `conversation_loop.py`)

1. `:2531-2533` — in-place surrogate / force-ASCII sanitize on the whole payload
   (surrogates cause non-retryable provider 400 "invalid unicode code point").
2. `:2534-2540` — codex `preflight_kwargs` (transport `agent/transports/codex.py:622`;
   normalizes input items, strips unsupported fields, bounds `prompt_cache_key`).
3. `:2544-2548` — Copilot `x-initiator: user` header (billing shape, first call of a
   user turn only).
4. `:2552-2567` — **LLM request middleware**: `apply_llm_request_middleware`
   (`hermes_cli/middleware.py:77-117`); afterwards `api_kwargs = payload`,
   original kept in `_original_api_kwargs`, applied trace in `_llm_middleware_trace`.
5. `:2636-2637` — MoA-only private field `_moa_prepared_request` appended AFTER the dump.

## 4. Dispatch and the TRUE SDK call sites

Non-streaming (all modes funnel through one function):
`_dispatch_nonstreaming_api_request` `agent/chat_completion_helpers.py:497`.
- codex: `_run_codex_stream` (`run_agent.py:5363`) → `agent/codex_runtime.py:1246`
  `run_codex_stream`; FINAL wire call `responses.create(**stream_kwargs)` with
  `stream=True` injected at `:1286-1289`.
- anthropic: `_anthropic_messages_create` (`run_agent.py:6108`) →
  `create_anthropic_message` (`agent/anthropic_adapter.py:3130`); FINAL is
  streaming-first `messages.stream(**kwargs)` → `get_final_message()` `:3166-3191`,
  fallback `messages.create()` `:3202-3204`.
- bedrock: pops the two sentinels `:539-540`, then `client.converse(**api_kwargs)`
  `:543` (boto3).
- moa: `agent.client.chat.completions.create(**api_kwargs)` `:555` (in-process facade).
- default OpenAI wire: `request_client.chat.completions.create(**api_kwargs)` `:557`.

Streaming: `interruptible_streaming_api_call` `chat_completion_helpers.py:2739`.
- OpenAI wire: `_open_stream` `:3292-3315` builds a COPY with `stream=True`,
  `httpx.Timeout(...)`, `stream_options={"include_usage":True}`; FINAL create at `:3315`.
- Bedrock streaming is inline here: `_open_bedrock_stream` `:2826-2832`
  (`client.converse_stream`), IAM fallback to `converse()` `:2850-2852`.
- codex/anthropic delegate to the non-streaming entry (they stream internally).

Inline (no worker thread) path: `should_use_direct_api_call` `:560-601` returns true
for cron platform, delegated-child context, or subagent platform → `direct_api_call`
`:637`. Same `_dispatch_nonstreaming_api_request` underneath.

## 5. Existing request dump helper

`dump_api_request_debug` — `agent/agent_runtime_helpers.py:1836-1928`
(forwarder `agent._dump_api_request_debug`, `run_agent.py:2946-2955`).
- Call sites: preflight (gated by env `HERMES_DUMP_REQUESTS`) `conversation_loop.py:2631`;
  `non_retryable_client_error` `:5514-5516`; `max_retries_exhausted` `:5855-5857`.
- Behavior: deepcopy body minus `timeout`, stamp `{timestamp, session_id, reason,
  request:{method POST, url, headers{Authorization masked}, body}, error?}`;
  redacts via `redact_sensitive_text(force=True)`; writes
  `logs_dir/request_dump_<safe_sid>_<ts>.json` atomically; optional stdout print under
  `HERMES_DUMP_REQUEST_STDOUT`; returns `Path` or `None`.

## 6. Dump limitations (checked against current code)

1. URL/method are fabricated for non-OpenAI wires (`:1867` hardcodes
   `/responses` or `/chat/completions`): anthropic is `/v1/messages`, bedrock is
   boto3 (no HTTP URL), MoA is in-process; headers (Bearer) are wrong for
   anthropic (`x-api-key`) and bedrock (SigV4).
2. Preflight snapshot precedes dispatch-time mutation: no `stream=True`/
   `stream_options`/httpx Timeout (added `:3293-3305` and `codex_runtime.py:1287-1288`);
   MoA `_moa_prepared_request` appended after the dump (`:2636-2637`); bedrock body
   still carries the two sentinels that are popped before boto3 (`:539-540`).
3. No size cap/truncation; regex redaction only; dumps carry the FULL body and give
   no token accounting — for context-bloat audits re-derive tokens with
   `estimate_request_context_tokens` (`chat_completion_helpers.py:79-129`, handles
   `messages`/`input`/`instructions`/`tools` shapes; consumed by
   `run_agent._compute_non_stream_stale_timeout` `:1435-1454`) or
   `agent/context_breakdown.py` categories.
4. Failure-triggered only (plus the env-gated preflight); no success-path archive,
   no retry-payload dedup.
5. API key harvest is OpenAI-client-only (`agent.client.api_key` `:1857`); auth header
   is masked so anthropic/codex/bedrock keys are absent from metadata.

## 7. Instrumentation insertion points (for a "context report" dump)

- **P1 (recommended):** extend the preflight gate `conversation_loop.py:2630-2631` —
  sees assembled api_kwargs for ALL modes post-middleware; already env-gated + has the
  dump helper and `logs_dir` wired. Caveat: pre-stream-flag and pre-boto3-pop snapshot
  (fine for context accounting since tokens live in `messages`/`input`/`instructions`/
  `tools`, unchanged by dispatch).
- **P2:** instrument `build_api_kwargs` returns (`:1330-1614`) with
  `estimate_request_context_tokens` breakdown + `context_breakdown.py` per-category
  tokens; maps 1:1 to compression thresholds (`run_agent.py:1435-1454`).
- **P3:** capture true wire payloads at the SDK boundaries for full fidelity:
  `:557`, `:3293-3315`, `codex_runtime.py:1286-1289`,
  `anthropic_adapter.py:3166-3204`, `:2826-2852`.
- **P4:** reuse the sanitized request-view pattern `_api_request_payload_for_hook`
  (`run_agent.py:2850-2862`) with usage added, for request-vs-response cost parity.

## 8. Test targets for payload/dump work

- `tests/run_agent/test_run_agent.py::test_logs_dir_retained_for_request_dumps` (`:504`)
  — the only existing request-dump regression test.
- `tests/run_agent/test_run_agent_codex_responses.py` — `test_build_api_kwargs_codex`
  (`:278`), `test_build_api_kwargs_xai_oauth_sends_cache_key_via_extra_body` (`:926`),
  preflight tests (`:691`, `:743`, `:776`, `:851`).
- `tests/agent/test_non_stream_stale_timeout.py` — `estimate_request_context_tokens`
  consumers.
- `tests/hermes_cli/test_plugins.py::test_plugin_can_register_and_invoke_middleware`
  (`:248`), `test_middleware_helpers_skip_no_listener_work` (`:277`) — middleware seam.
- `tests/run_agent/test_wire_context_pruning.py` — wire pruning feeds the messages
  that reach `build_api_kwargs`.
- Suggested new: `tests/run_agent/test_request_dump_fidelity.py` asserting per-mode
  dump URLs (anthropic `/v1/messages`, bedrock sentinel pop, stream flag) — none exists.
