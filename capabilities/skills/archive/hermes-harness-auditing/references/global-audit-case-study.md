# Global Hermes harness audit — condensed case study (2026-07-13)

This reference preserves the reusable lessons and evidence shape from one real audit. Values are historical snapshots, not current system truth.

## Scope

Audited a dirty local Hermes worktree end-to-end:

`Desktop → tui_gateway WebSocket/JSON-RPC → session → AIAgent → turn context → provider transport → tools → compression → SessionDB → outbound events`

Also mapped CLI, dashboard/API, and the separate messaging `gateway/` surface.

## Corrections that mattered

1. **Gateway confusion**: an early sub-audit mixed `gateway/run.py` with the Desktop path. Direct code inspection established that Desktop uses `tui_gateway/`; messaging channels use `gateway/`. Both converge later on the agent core.
2. **Unsupported root cause**: “agent loop buffer saturation / JSON deserializer latency” had no OOM, traceback, queue-depth, or profiling evidence. Runtime logs instead showed repeated compaction and session rollover. The report explicitly retracted the unsupported claim.
3. **Provider scope**: a Kie transport investigation had initially been framed as the global report. It was archived and retained only as an appendix proving actual Responses-body and usage behavior.
4. **Reconstructed versus captured payload**: the provider body was reconstructed from transport inputs, not captured on the wire. The wording was corrected before delivery.
5. **Artifact verification**: several plausible summary numbers were removed or corrected after checking the source report and DB. Hashes were recomputed after the final write.

## Validation pattern

A monolithic pytest command stopped during collection because one local test imported a removed symbol. Splitting the suite exposed the real state:

- 575 Python tests passed across Gateway, transports, compression, tools/DB, and a dedicated regression;
- one Python file remained collection-skewed;
- 88 Electron Node tests passed;
- Desktop Vitest was 97/98, with one stale expected payload;
- TypeScript passed;
- ESLint still had one error and two warnings;
- SQLite `quick_check` and `git diff --check` passed.

Lesson: report independent pass counts and skew separately; never let a collection error erase successful evidence.

## High-value findings

### Compression lineage

The logical Desktop conversation was represented by rapidly changing physical sessions. A frozen metric snapshot recorded 136 segments; a live follow-up reached 140 shortly afterward. Median segment duration was about 42 seconds. Locks prevented some races but did not rate-limit rollovers.

### Secret persistence

A read-only syntax scan found secret-shaped candidates in user/tool content. Values were never printed or tested. Code inspection showed no universal pre-write redaction for all message roles, and FTS indexes duplicated persisted content. The finding was therefore critical even though credential validity remained unknown.

### Worker ownership

Five `slash_worker` processes existed. Only two were classified as leaks after correlating process age and session state: one belonged to an ended compression segment and one had no DB session. The others remained unknown rather than being called orphans by age alone.

### Storage and observability

The DB was about 2.1 GB and FTS objects occupied roughly 71% of it. This justified profiling index value before deletion, not blind cleanup. Failed provider attempts and unknown model prices made recorded cost a lower bound rather than a bill.

## Provider annex discipline

The Kie case proved useful facts about the Responses transport:

- endpoint selection;
- reconstructed body composition;
- provider-reported input/output usage;
- strict rejection of an invalid tool schema.

It did **not** prove the Desktop E2E path or describe the whole harness. The invalid tool schema was framed as a harness/provider-compatibility issue potentially reproducible with any strict provider.

## Delivery verification

The final report was checked for:

- complete required headings;
- valid metrics JSON;
- embedded metrics hash matching the current file;
- zero secret-shaped values in the report;
- absence of stale/unverified numbers;
- archive banner on the superseded Kie report;
- clean whitespace via `git diff --check`.

The final report path for this historical case was:

`/root/.hermes/hermes-agent/.hermes/reports/hermes-harness-global-audit-2026-07-13.md`
