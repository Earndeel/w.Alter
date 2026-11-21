# Platform operations decision tables

## State boundaries

| Boundary | Verify separately |
|---|---|
| Config | Active `HERMES_HOME`, profile, file path, YAML types |
| Runtime | Interpreter, process owner, PID, bind, loaded version |
| Transport | Provider/model, endpoint, API mode, stream and tool schema |
| Persistence | Session DB, memory store, cache/snapshot, raw tool pairing |
| Client | Dashboard/Desktop/TUI origin, host-header trust, WebSocket path |

## Safe service changes

1. Discover the owner and current PID before restart.
2. Make the smallest reversible change.
3. Restart only the owner of changed code/config.
4. Read back process, endpoint, logs, and client state.
5. Run a focused test and a real Hermes-path canary.

A dashboard port and an `api_server` port are different surfaces. Keep remote exposure loopback-bound behind an approved tunnel or authenticated proxy. Put adapter keys such as `host` and `port` under `extra` when the adapter reads that mapping.

## Delegation evidence

Preserve this chain in diagnostics:

```text
requested objective/tools
  -> resolved child profile/tools
  -> registered child functions
  -> provider schemas
  -> function call
  -> Hermes tool result
  -> child continuation/final result
```

A direct provider request or text-only facade does not prove an agentic worker. Preserve inherited permissions, cancellation, session lineage, usage, and cost status.

## Memory and session evidence

- SQLite `state.db` is verbatim session history; Hindsight/PostgreSQL is extracted durable knowledge; Qdrant/hybrid search is an index.
- Keep assistant tool calls paired with tool results across compaction and provider conversion.
- Treat recalled memory as an ephemeral user-turn projection; gate trivial prompts and report score/budget limits only when the exercised API exposes them.
- Count logical text separately from physical FTS, snapshots, and vector mirrors.

## Async jobs

Persist provider/task correlation before polling. Verify callback signatures and replay protection, use monotonic idempotent transitions, poll with bounded backoff, and download expiring results immediately. A callback may be completion-only.

## Update safety

Keep custom policy outside the Hermes checkout where possible. Replay patches on a clean base, test in an isolated home, prove incompatible configuration fails closed, and verify plugin discovery and rollback construction after the update. Never reset or delete an unexplained state database.

## Payload and compression procedure

1. Resolve the live config and instantiate the compressor through its real initialization path without invoking a completion. Record resolved context length, output reservation, effective ratio, token trigger, tail budget, proactive threshold, minimum reclaim and cooldown. Model-specific overrides and small-window floors can override the configured ratio; verify propagation of `compression.threshold_tokens` before using it as an absolute trigger cap.
2. Trace request assembly through the provider adapter and SDK serialization. Count bytes at that final boundary and label token estimates separately from provider usage. Attribute tool outputs through every matching call ID, including reordered parallel results and different provider message formats; a zero skill subtotal may be an attribution bug, not an absence of skill content.
3. Replay bounded historical samples using indexed, read-only database queries. Preserve raw history and avoid a full database copy for a payload audit. Include system text and schemas in the denominator; label substituted current schemas or missing checkpoint state as reconstruction rather than historical wire evidence. Store sizes, hashes and IDs, not raw user text or secrets.
4. Compare native settings before introducing code. Test a full-compression trigger cap separately from earlier proactive pruning so a safe cap is not bundled with unsafe deletion. A reduction that discards older required skill documents is a failed acceptance case even when the last messages and tool IDs survive; raising a size floor until savings vanish is not a useful optimization either.
5. Verify preservation at content level: current user request; required main and linked procedures; pending parallel groups outside a fixed last-N tail; assistant-call/result pairing; historical identifiers and decisions. For any duplicate detection, distinguish references and changed document contents rather than matching skill name alone. Append another turn, change configuration, replay the session and verify the existing provider prefix stays identical outside explicit compaction.
6. Reproduce summary failure with injected HTTP server errors after existing fallback resolution. Compare the complete pre/post message list, system bytes, previous summary, compression counter and cooldown behavior. Then supply a successful permitted fallback and verify it commits normally. Report aborted attempts as no savings; a fallback-attempt flag alone does not prove a static fallback replaced history. When an outage prevents an already-overflowing request from shrinking, report that limit instead of claiming a hard budget guarantee.
7. Run the candidate checkout's official runner with temporary `HOME` and `HERMES_HOME` and the verified interpreter. Search the test tree for changed dispatch symbols before editing helpers; repair obsolete mocks to reach the actual dispatch path rather than waiving a failing E2E. Use real imports, persistence and SDK serialization without network for deterministic coverage; label mocked summaries and document-only loading explicitly, since neither proves real model quality or procedure execution.
8. Roll out only changes with justified benefit. Separate reliability and measurement fixes from rejected projector experiments; preserve inherited dirty changes. After installing and validating rollback, activate authorized backends and verify exact source/config hashes, effective settings, new process identities and endpoint health. Do not infer request savings from the new trigger alone.

## Explaining the active payload and cache behavior

Use this read-only workflow when Monsieur asks what each call contains or whether compaction retains a raw tail; do not turn an explanation into a configuration change.

1. Read the active engine selector and compression settings, then inspect the registered plugin and native implementation. Resolve effective values through initialization when a numeric guarantee matters; configuration alone does not prove a code path is exercised.
2. Follow ordinary request assembly separately from summary generation: `build_api_messages` → `assemble_api_request` → provider serialization. Inspect the engine's selection hook, summary-policy hook and recovery schema. Explain stable instructions, exposed tool schemas, retained conversation, current-turn memory additions and newly appended tool results as separate blocks. Skills and recovered history enter through tool results when requested; storage existence is not automatic injection. Label this as code-derived structure unless a final request was actually captured.
3. Inspect `_find_tail_cut_by_tokens`, its budget walk, native message-floor cap and user/assistant anchors before interpreting `protect_last_n`. Verify tool-group alignment and separately inspect deduplication, image eviction and provider sanitization. Describe a tail as non-summarized rather than byte-identical when those transformations apply; do not equate message count with user-turn count.
4. Trace `prune_tool_results_only` to its preflight caller. Read the trigger, eligible size, minimum reclaim, rearm condition and archive-before-commit behavior. Explain that age/size/dedup rules are deterministic heuristics, not evidence-consumption tracking; check exceptions before promising the tail is untouched.
5. Show the sequence as stable accumulation → eligible deterministic cleanup or goal-conditioned summary → retained head/summary/recent tail → further appends. Distinguish a boundary-only policy in the existing summary request from an additional classifier call, automatic source retrieval or a rolling summary on every call.
6. Explain that any accepted historical rewrite can invalidate cache from the first changed token. Minimum-reclaim and rearm gates reduce rewrite frequency, but do not prove an optimal cost tradeoff; transport/provider cache behavior and billed usage need separate measurement. A disabled micro-compaction setting does not disable every native pruning or send-time transformation.
7. Close with what is implemented, what is conditional and what remains unmeasured. Avoid calling borrowed recoverability or goal guidance a repaired or fully integrated upstream LCM/U-Fold system.

## Context-engine qualification

Use this sequence when replacing or extending the native compressor; qualify the existing extension before deciding to reuse it or build another storage layer.

1. Freeze the candidate revision and actual host source hashes, including dirty changes. Read the host's registration, initialization, argument filtering, attempt snapshot/restore, session binding and cancellation call sites. Enumerate the helpers the host really invokes, including durable binding, timeout/rejection bookkeeping, structural-no-op backoff and emergency cooldown bypass; implementing the nominal interface alone does not establish lifecycle compatibility.
2. Run the same lifecycle fixtures against the native baseline and the candidate through real imports and the official runner in isolated homes, with network disabled and summaries mocked. Exercise real host orchestration and SessionDB for commit, database rejection, cancellation, detached timeout, reset/rebinding, fallback, in-place commit and rotation. Inject a DB refusal after summary generation and compare transcript, previous summary, counter and durable cooldown rather than only returned messages. For the reset race, block the summarizer with an Event, rebind A→B, write a distinctive cooldown sentinel in B, release A and read back both sessions and B's sentinel; stale failure bookkeeping can cross sessions even when transcript publication is fenced. Also test reset back to the same session identity so generation changes are not mistaken for continued ownership. Exercise actual snapshot/restore helpers, and identify hook-level concurrency tests separately from a full gateway reset reproduction; neither deepcopy nor native inheritance proves rollback safety.
3. Qualify canonical history before adding another archive: commit synthetic messages through both in-place compaction and rotation, then read inactive originals back and compare IDs, roles, content and tool metadata. Distinguish retained original IDs from newly inserted tail clones; preserved rows alone do not establish a complete retrieval API. Test server-enforced source/output limits, within-message continuation and authorized compression ancestry, excluding unrelated sessions and sibling branches. Bound SQL content reads before materialization rather than loading a whole message and slicing afterward; caller-supplied token limits must not bypass the server cap. If separate file archives are necessary, also reproduce symlinked paths, malformed lineage, oversized sources and a giant message with `limit=1`; validate ownership, no-follow access, regular files and storage quotas independently of content digests. Qualify local filesystem prerequisites honestly rather than calling a planted-symlink fixture arbitrary remote disclosure.
4. Place a complete historical skill exchange in the compressible middle and repeat compaction. Verify that required instructions are selected before summary dispatch, complete tool groups survive and structural rejection backs off. Distinguish active procedures from all historical skill operations; preserving everything indiscriminately can prevent compaction forever.
5. Change models and verify both exposed and internal usage reset, explicit thresholds propagate and actual tool-schema/output headroom is accounted for. Measure acceptance in tokens at the request boundary, not JSON-byte shrinkage. Treat summary targets and retained-tail budgets as distinct configured values, neither as measured final summary size.
6. Add adversarial validator fixtures with identical text in old and current user messages, reordered messages and duplicate tool-call IDs. Assert stable current-request identity/order and unique complete call/result groups; set membership and first matching text can accept a malformed transcript. Label deliberately malformed fixtures as validator tests, not naturally observed summarizer behavior.
7. Test useful-context selection with fixed histories and different current goals: preserve the exact request, unresolved constraints, active instructions and needed evidence while retiring completed detail into bounded recoverable sources. Require no extra summary calls or prefix rewrites between explicit compaction boundaries. An archive, relative trigger and generic focus sentence do not demonstrate task adaptation. Do not silently promote a proposed selection algorithm into a validated implementation.
8. Produce separate gates for lifecycle/security, usefulness and measured model/cache performance. Read the assertion intent as well as the test count; passing defect-reproduction tests mean the candidate remains blocked. Record unexercised host orchestration paths explicitly. Activate only after the relevant gates pass and activation is authorized; an existing LCM implementation is a qualification candidate, not automatic approval.

## Restarts that outlive the agent

1. Discover the exact service owner and scope; user and system units may own different Hermes surfaces.
2. Prepare a narrowly scoped activation script that validates expected pre-change hashes/PIDs, restarts only authorized owners, checks health, and atomically writes an explicit success or failure receipt.
3. Launch that script through an independent supervisor such as `systemd-run`; its launch exit status means the supervisor accepted the job, not that activation succeeded.
4. After reconnecting, read the durable receipt and independently verify the target PIDs and health endpoints. Treat a delegation-owner exit as an unknown result until these checks resolve it; do not duplicate the restart.

## Evidence labels

Use `MEASURED`, `OBSERVED IN CODE`, `RISK`, and `UNKNOWN`. A successful HTTP status, visible picker row, passing unit test, or process label proves only the layer it exercised.
