# End-to-end Hermes harness payload audit

Use this reference when a request targets the **whole Hermes harness**, not one provider. The figures below are a dated session snapshot; re-measure them on the active checkout.

## Scope model

Treat the harness as four distinct payload boundaries:

1. **Client → Gateway envelope** — Desktop/TUI sends a small JSON-RPC request such as `prompt.submit`; this is not the model payload.
2. **Gateway → Agent state** — session creation/resume, history reconstruction, platform/cwd/toolset resolution, cancellation, event callbacks.
3. **Agent → Provider request** — system/instructions, selected history, memory, tool schemas, cache metadata and provider-native serialization.
4. **Agent/Gateway → Persistence** — session lineage, canonical messages, tool calls/results, token/cache usage and FTS indexes.

JSON-RPC applies to the client/gateway boundary. Do not describe internal agent calls, tool execution or every provider request as JSON-RPC; each provider transport has its own body.

## Scope guardrail

A provider-specific failure is a **case study**, not the audit perimeter. When a provider incident initiates the work:

- keep every valid measurement about system prompt, tools, cache, compaction or serialization;
- label transport-specific conclusions explicitly;
- map every ingress, shared agent stage, transport family and persistence boundary before claiming “full harness” coverage;
- put the provider deep dive in an appendix rather than discarding it or letting it replace the system report.

Before writing the verdict, include a coverage matrix with at least: Desktop/TUI ingress, gateway dispatch, session resume, agent loop, tool execution, compaction, OpenAI-compatible chat, Responses/Codex, Anthropic, Bedrock, streaming response, state DB and observability.

## Measurement pitfalls

### Measure the runtime composition, not the CLI label

`hermes prompt-size --platform desktop` may represent the nominal Desktop profile while the running gateway resolves another platform and loads CLI toolsets through its own helper. Inspect the gateway's actual platform, enabled toolsets and session `cwd`, then build the measurement with those exact values.

### The working directory is payload input

Running `prompt-size` from the repository can include large project context files that are absent from a session whose real `cwd` is the home directory. Always record both the command working directory and the session working directory. A large difference is a diagnostic fact, not automatically a production payload.

### Separate static and dynamic budgets

Report independently:

- system/instructions bytes and tokens;
- tool-schema bytes and tokens;
- dynamic message/history tokens;
- cached versus uncached provider input;
- tool-result volume;
- persistence/index storage.

Static tool schemas are often the best cache candidates; dynamic tool outputs are usually the larger context-growth pressure. Do not recommend deleting useful stable context before quantifying cache reuse.

### Test in the service runtime

Use the same Python environment and checkout as the running Hermes service. Classify collection failures caused by the wrong interpreter separately from genuine assertion failures. On a dirty checkout, identify modified/untracked tests before treating a red test as a baseline regression.

## Session snapshot: 2026-07-13

Observed during a local audit, subject to re-measurement:

- nominal Desktop/TUI prompt-size output was much smaller than the gateway composition because the gateway loaded CLI toolsets;
- running prompt-size from the repository added a large project-context block absent from the actual home-directory session;
- a Kie Responses request provided useful transport evidence but did not cover Chat Completions, Anthropic, Bedrock, Desktop RPC or persistence;
- `state.db` was about 2.07 GB, with FTS/trigram structures dominating physical storage and tool results dominating message content;
- the selected backend matrix reached 219 passing tests before two model-aware threshold assertions failed; the selected Desktop matrix reached 156 passing tests with one session-resume contract mismatch.

These numbers belong in an appendix or metrics artifact, never as timeless defaults.
