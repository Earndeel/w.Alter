# Retention Code Map — audited file:line (2026-08-17, main / dirty tree)

Read-only audit outcome for why full skill content and raw tool results remain in
the active payload, and exactly where the reclaim hooks live. Every hook is cited
`file:line` against the Hermes repo.

## Skills index — rendered in full, no budget

- `agent/prompt_builder.py:1660` `build_skills_system_prompt()` renders the ENTIRE
  visible index (every category + skill name + description) into `<available_skills>`
  (`agent/prompt_builder.py:1890-1953`). No token/byte budget.
- Placed first in the system-prompt volatile tier at `agent/system_prompt.py:521`,
  wired in via `agent/system_prompt.py:299-327` when skills tools are present.
- Cached on `agent._cached_system_prompt` for the session (`agent/system_prompt.py:569-595`),
  invalidated only on compression (`invalidate_system_prompt` `:598-607`).
- LRU + disk snapshot cache key (`agent/prompt_builder.py:1696-1704`) has NO budget
  component — adding budget inputs would correctly invalidate the cached snapshot.
- Only built-in reduction: coding-posture `compact_categories` → names-only lines
  (`agent/prompt_builder.py:1874-1897`); nothing is ever hidden or byte-budgeted.

## skill_view — first load persists forever

- `tools/skills_tool.py:1085` `skill_view()` returns the whole SKILL.md as a JSON
  tool-result string; no content cap.
- Registry: `skills_list` at `tools/skills_tool.py:1927`; `skill_view` at `:2093`
  routed to handler `_skill_view_with_bump` `:2049-2090`.
- Repeat-view dedup `_check_skill_view_dedup` `tools/skills_tool.py:1994-2033` stubs
  ONLY the SECOND view of the SAME unchanged file per task — the first full load
  stays in history every later turn.
- `reset_skill_view_dedup` `tools/skills_tool.py:2036-2046` runs ONLY on full context
  compression (`agent/conversation_compression.py:3654-3660`).

## Raw tool-result reclaim — both paths non-default

1. Full compression: `should_compress`/`should_compress_info`
   `agent/context_compressor.py:2906-2952` (~50% of window). Loop wiring:
   `agent/conversation_loop.py:2248-2365` (pre-API gate) and `:2366-2392`
   (cooldown warn elif).
2. Proactive prune `prune_tool_results_only` `agent/context_compressor.py:3391`:
   gated on `proactive_prune_tokens > 0`, which DEFAULTS TO 0
   (`hermes_cli/config_defaults.py:644`); commit gates min-reclaim + rearm runway
   (`:3432-3441`; constructor knobs `:2566-2591`). Loop arm already wired at
   `agent/conversation_loop.py:2366-2392` (getattr-guarded, commits on
   `result is not input`).

## prompt_view — unwired on this checkout (key finding)

- `agent/prompt_view.py:152` `slim_prompt_history(agent, messages)`: deterministic
  digest of consumed/oversized tool results → `[TOOL RESULT DIGEST]` /
  `[SKILL ALREADY LOADED]` marker + `state_db://session:<id>/tool_call:<id>` recall
  handle (`_digest` `:126-149`); byte-stable / idempotent on re-application.
- Referenced ONLY by the module + `tests/run_agent/test_wire_context_pruning.py`
  — never imported by `run_agent.py`, `agent/conversation_loop.py`,
  `agent/chat_completion_helpers.py`.
- E2E wiring test `test_run_conversation_sends_digest_but_keeps_raw_transcript`
  (`tests/run_agent/test_wire_context_pruning.py:181-262`) is RED; its 10 unit
  tests (`:36-178`) pass ⇒ call site missing, logic fine.
- No config key; the module reads `agent._tool_result_prompt_view_config`
  (normalize fn `agent/prompt_view.py:20-40`), which nothing sets in production.

## Fix locations

| Ask | File:line |
|---|---|
| Wire prompt-view slimming | `agent/conversation_loop.py:2506-2516` before `_build_api_kwargs(api_messages)`; alt `agent/chat_completion_helpers.py:1330-1371`; populate `agent._tool_result_prompt_view_config` in `agent/agent_init.py` + default in `hermes_cli/config_defaults.py` |
| JIT skill loading / bounded category budgets | `agent/prompt_builder.py:1660` (param), renderer `:1890-1953` (names-only/budget-capped, extend `compact_categories` `:1874-1897`), cache key `:1696-1704`, snapshot paths `:1711-1761`; caller `agent/system_prompt.py:321`; config block `hermes_cli/config_defaults.py:644-689` |
| skill_view excerpt/budget mode | `tools/skills_tool.py:2049` / `:1085` — match `prompt_view._digest` (`agent/prompt_view.py:126-149`) |
| Proactive per-category compaction | `agent/context_compressor.py:3391` `prune_tool_results_only` (add per-category budgets); loop arm `agent/conversation_loop.py:2366-2392`; post-compaction re-view `agent/conversation_compression.py:3654-3660` |
| Definition of done | turn `tests/run_agent/test_wire_context_pruning.py:181-262` green |

## Compressor lifecycle / active flags (context)

- Engine selection + construction: `agent/agent_init.py:2431-2550` (plugin vs
  built-in `ContextCompressor`; proactive_prune knobs `:2529-2550`;
  `agent.compression_enabled` `:2557`).
- Class `agent/context_compressor.py:1577`; `__init__` `:2513`;
  `on_session_reset` `:1592-1634` resets `_active_compression_telemetry` `:1623`,
  `_proactive_prune_rearm_tokens` `:1625`, micro-compaction state `:1627-1634`.
- Gates: `_automatic_compression_blocked` `:3000`,
  `_automatic_compression_blocked_locally` `:3014` (cooldown + anti-thrash
  `:3051-3088`), `get_active_compression_failure_cooldown` `:2131`, `update_model` `:2293`.
- Host lifecycle transitions (`on_session_end/start/reset`): `run_agent.py:675-792`
  `_transition_context_engine_session`.
- Post-compression dedup resets: `agent/conversation_compression.py:3646-3660`
  (`reset_file_dedup` `:3651`, `reset_skill_view_dedup` `:3657`).
