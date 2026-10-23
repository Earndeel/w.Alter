# GPT-5.6 Hermes verification evidence

## Purpose

Session-specific evidence pattern for validating Kie.ai GPT-5.6 (`gpt-5-6-luna`) as a real Hermes agent backend. Keep this separate from the class-level procedure in `SKILL.md`.

## Reproduction checklist

1. Use a temporary Hermes config/copy; never alter production while probing a custom Responses provider.
2. Verify `KIE_API_KEY` is present without printing it.
3. Limit direct probes to a few paid calls. For each probe record only HTTP status, response ID, response model, completion status, reasoning metadata, usage, tool-call shape, and credit field.
4. Test the candidate reasoning field explicitly. Treat an echoed `reasoning.effort=max` as unverified when usage reports `reasoning_tokens=0` or the response reports standard reasoning.
5. Run Hermes with at least one tool schema, capture the outbound request, and inspect its actual URL and body. Do not call a PONG-only response an agentic validation.
6. Inspect the temporary SQLite session row: `model`, `billing_provider`, `billing_base_url`, token counts, and end state. A plausible answer without Kie billing metadata is not proof of routing.
7. Write a redacted JSON report before the final narrative, including absolute artifact paths and a verdict: `OK`, `OK_ADAPTER`, or `KO`.

## Evidence from the July 2026 probe

- `/tmp/hermes-kie-test/test2_response.json`: direct Responses call returned `status=completed`, a function call, `credits_consumed=0.01`, response model `gpt-5.6-luna`, and request reasoning effort `max`; it also reported `reasoning.mode=standard` and `reasoning_tokens=0`. This proves transport + single-turn tool shape, not maximum thinking.
- `/tmp/hermes-kie-test/run_test.py`: bounded direct test design for connectivity, tool call, streaming, and multi-turn tool loop. Do not rerun wholesale without preserving the call cap.
- `/tmp/hermes-kie-test/home/sessions/request_dump_*.json`: Hermes sent `POST https://api.kie.ai/codex/v1/responses` but received HTTP 403 `Your request was blocked`; the captured request used `reasoning.effort=medium` in the tested run, so it did not prove Hermes max-thinking propagation.
- `/tmp/hermes-kie-test/home/state.db`: the failed Hermes sessions had null `billing_provider` and `billing_base_url`, so no successful Kie routing or fallback success could be claimed.

## Reporting rule

State separately: direct Kie reachability, reasoning control confirmation, Hermes transport compatibility, tool-loop continuity, and fallback/billing verification. If any layer is unproven, use `OK_ADAPTER` or `KO`, never a blanket “working.”

## Rerun 2026-07-10 evidence

- `/tmp/hermes-kie-test-rerun/direct_calls.json`: 3 appels directs, 2 OK (reasoning.effort=max nested), 1 KO (reasoning_effort=max flat → 500 serveur). Confirmed: seul le format nested `reasoning.effort` est accepté ; le flat `reasoning_effort` casse l'API.
- `/tmp/hermes-kie-test-rerun/home/sessions/request_dump_*.json`: Hermes v0.18.2 envoie le bon format Responses (`POST /codex/v1/responses`, champs `input`, `tools`, `reasoning`) — le downgrade vers `chat_completions` ne se produit PAS. Mais HTTP 403 car User-Agent browser-like absent. Le payload porte `reasoning.effort=medium` malgré `reasoning_effort: max` dans le config.
- `/tmp/hermes-kie-test-rerun/home/state.db`: `billing_provider=null`, `billing_base_url=null` — échec pur, pas de fallback.
- `/tmp/hermes-kie-test/rerun_report.json`: rapport machine-readable final avec verdict `KO` et root causes (403 Cloudflare + reasoning_effort non propagé).
- Amélioration vs probe initiale : le format Responses est correctement préservé par Hermes (pas de downgrade), la preuve du format nested vs flat du champ reasoning est acquise, et la cause du 403 est identifiée (UA manquant, pas un problème de format de payload).

## 2026-07-12 full direct checkup (6/6 PASS)

First fully successful direct probe — all calls used the correct Chrome User-Agent, SSE parsing, and `reasoning_tokens` extracted from `usage.output_tokens_details` (not the top-level key that doesn't exist).

### Artifacts
- `/tmp/kie-gpt56-full-checkup.json`: machine-readable report, 4 paid calls, 6 verdicts all PASS.
- `/tmp/kie-gpt56-full-checkup/call{1,2,3,4}_raw_sse.txt`: complete raw SSE streams for all 4 calls.
- `/tmp/kie-gpt56-full-checkup/call1_low.json`: `effort=low` → `status=completed`, `reasoning_tokens=294`, output `["reasoning", "message"]`.
- `/tmp/kie-gpt56-full-checkup/call2_max.json`: `effort=max` → `status=completed`, `reasoning_tokens=4134` (14.1× low), output `["reasoning"×8, "message"×2]`. **Effort propagation proven at scale.**
- `/tmp/kie-gpt56-full-checkup/call3_tool_call.json`: `function_call` returned with `type=function_call`, `name=add_numbers`, `arguments={"a":12345,"b":67890}`, `call_id=call_ZnRFdZ44z1D3ozXOMHzynEdb`.
- `/tmp/kie-gpt56-full-checkup/call4_tool_loop.json`: `function_call_output` submitted, final answer contains `80235` → complete agentic loop confirmed.

### Corrections vs prior probes
1. **SSE parsing is mandatory** — endpoint always returns `text/event-stream`, even without `stream:true`. Prior probes calling `.json()` would have failed silently. Final response is inside `response.completed` SSE event.
2. **`reasoning_tokens` is nested** under `usage.output_tokens_details`, not at `usage.reasoning_tokens`. This explains why the July probe reported `reasoning_tokens=0` — wrong key.
3. **`credits_consumed` is always `null`** — endpoint doesn't return it.
4. **Chrome UA mandatory** for Kie Cloudfront. Without: 403. With: clean 200.

### Verdicts (all PASS)
transport, effort_propagation, thinking_observability, tool_call_shape, multi_turn_tool_loop, streaming (native SSE).
