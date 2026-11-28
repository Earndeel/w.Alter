# Remote Mac CuaDriver HTTP — research reference

## Status and scope

Research snapshot: 2026-08-05. This reference records upstream contracts and
architecture findings; the VPS-to-Mac CuaDriver HTTP path was not declared Mac
E2E-validated during the research session. Run the validation matrix in the
parent skill before treating it as production-ready.

## Primary finding

Hermes' built-in `computer_use` integration currently starts a local
`cua-driver` executable through MCP stdio. Its backend resolves the executable
on the Hermes host and its backend selector only chooses the local Cua backend
or a noop test backend. A Mac GUI reached through an SSH tunnel therefore needs
an explicit remote transport or an MCP HTTP configuration; a local VPS Cua
process cannot inherit the Mac user's TCC grants.

Relevant Hermes locations:

- `tools/computer_use/tool.py` — backend selection and per-session lifecycle.
- `tools/computer_use/cua_backend.py` — local executable resolution, stdio MCP
  lifecycle, capabilities, element tokens, action verdicts and recovery.
- `tools/computer_use/schema.py` — generic model-facing action vocabulary.
- `tools/mcp_tool.py` — existing Streamable HTTP client, headers, reconnect,
  env interpolation, and `tools.include` / `tools.exclude` filtering.
- `skills/devops/mac-computer-use-ssh` — legacy `screencapture` + `cliclick` +
  `osascript` server on the Mac.
- `skills/devops/ssh-mac-remote-control` — SSH/Tailscale tunnel operations.

## Upstream CuaDriver contracts

The CuaDriver repository documents three relevant properties:

1. `cua-driver mcp` normally speaks stdio to the host desktop.
2. The daemon has a loopback-only MCP HTTP transport, enabled by a configured
   port and a host-generated bearer token. The HTTP implementation accepts
   `POST /mcp`, rejects browser-origin requests, compares the bearer token in
   constant time, requires a token of at least 32 non-whitespace characters, and
   limits the HTTP body to 16 MiB. This is suitable for an SSH local-forward,
   not for an internet-facing bind.
3. On macOS, Accessibility and Screen Recording are attributed to the
   permission-owning app/process responsibility chain. The upstream embedding
   guide says to spawn the embedded daemon directly from the signed host app;
   do not use `open`, `NSWorkspace`, an unrelated gateway, or a raw executable
   launched from the wrong process and expect the app's grants to transfer.

Upstream sources:

- `https://github.com/trycua/cua`
- `https://cua.ai/docs/how-to-guides/driver/expose-mcp-from-desktop-app`
- `https://cua.ai/docs/reference/cua-driver/embedding`
- `https://cua.ai/docs/reference/cua-driver/mcp-tool-notes`
- `https://cua.ai/docs/how-to-guides/driver/connect-your-agent`

The upstream remote SDK also defines a useful generic contract even when the
actual carrier is implemented elsewhere: request IDs, envelope versions,
deadlines, authenticated principal, connection generation, cancellation, and a
`completion_known` flag. If the carrier loses a response after dispatch, the
client must classify completion as unknown and must not replay the side effect.

## Hermes zero-code POC

Use a separate forwarded port while the legacy W.Alter server remains on its
current port. The exact port and token are deployment choices; do not copy a
real credential into this file.

```yaml
mcp_servers:
  mac-cua-poc:
    url: "http://127.0.0.1:<forwarded-port>/mcp"
    headers:
      Authorization: "Bearer ${WALTER_MAC_CUA_TOKEN}"
    skip_preflight: true
    connect_timeout: 10
    timeout: 120
    tools:
      include:
        - start_session
        - end_session
        - check_permissions
        - list_apps
        - list_windows
        - get_window_state
        - screenshot
        - click
        - type_text
        - press_key
        - hotkey
        - scroll
        - drag
        - set_value
        - clipboard_*
```

Confirm the actual tool names through the live `tools/list` response before
writing the allowlist. `skip_preflight` is a compatibility option for a
POST-only MCP endpoint; it is not a way to bypass authentication. Resolve the
token through the active secret scope. Hermes already supports `${VAR}`
interpolation and Streamable HTTP headers in `tools/mcp_tool.py`.

This POC deliberately exposes raw Cua tools and is therefore a discovery and
host-validation path. It should not be left as the permanent model-facing
surface if a single generic `computer_use` tool can wrap it.

## Production integration shape

Refactor the existing local Cua backend around a transport interface rather
than duplicating the action parser:

```text
CuaDriverBackend
  ├── StdioCuaTransport       # existing local path
  └── StreamableHttpTransport # Mac tunnel path
```

Both transports should feed the same session/capability/action layers. The
remote backend must preserve:

- Hermes session ID → Cua `session` argument;
- per-session call lock;
- live `tools/list` capability and input-schema discovery;
- element token propagation and stale detection;
- screenshot MIME and dimension metadata;
- `effect`, `verified`, `escalation`, `path`, `degraded`, and `code`;
- remote request ID and completion-known state;
- explicit teardown and reconnect generation;
- existing Hermes approval and YOLO boundaries.

Do not add a second core model tool merely for the Mac. A configured raw MCP
server is acceptable for the POC; a remote transport behind the existing tool
keeps prompt footprint, approvals, multimodal result handling, and the
model-facing vocabulary stable.

## What to borrow from adjacent projects

### agent-desktop

`https://github.com/lahfir/agent-desktop` provides strong semantic contracts:
qualified refs containing a snapshot ID, `STALE_REF`, `AMBIGUOUS_TARGET`,
actionability preflight, `wait --predicate actionable`, batch execution, C ABI,
clipboard operations, and JSONL traces. Its default semantic operations are
headless, while physical click/drag/hover require an explicit headed mode.
Use these as design targets; the project is a local CLI/C ABI, not a drop-in
remote Mac transport.

### ClawdCursor

`https://github.com/AmrDab/clawdcursor` documents a useful perception and
verification ladder: accessibility tree, local OCR, then screenshot/vision only
when required. Its `expect` / `DEVIATION` concept is stronger than a generic
transport success flag, and its single safety gate plus human kill switch are
worth copying conceptually. Validate its Mac TCC and remote HTTP behavior
independently before adopting code.

### Ghost OS and OpenAdapt

`https://github.com/ghostwright/ghost-os` is relevant for AX-first,
vision-local, self-learning Mac recipes. `https://github.com/OpenAdaptAI/OpenAdapt`
is relevant for trace/replay and deterministic workflows. Neither should be
introduced as the low-level remote driver before the Cua transport is stable.

### Qwen open-computer-use

`https://github.com/QwenLM/open-computer-use` is a useful reference for
macOS `SCScreenshotManager`, post-action screenshots, image-size budgets, and
coordinate rescaling. It is primarily a local MCP/CLI service, so it does not
solve the VPS-to-Mac transport by itself.

### Official model computer-use APIs

- OpenAI: `https://developers.openai.com/api/docs/guides/tools-computer-use`
- Anthropic: `https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool`
- Gemini: `https://ai.google.dev/gemini-api/docs/computer-use`

All three require client-side execution. Their durable lesson is the custom
harness loop: capture, return an action, execute on the client, capture again,
keep humans at high-impact boundaries, treat screen/page content as untrusted,
and never mistake model intent for execution proof. Gemini's safety decision
and prompt-injection detection can inspire a policy layer, but neither solves
TCC or SSH.

## Legacy W.Alter v5 migration warnings

The existing template is a pixel-only compatibility path:

- full-screen `screencapture`;
- `cliclick` cursor/input operations;
- `osascript` keyboard synthesis;
- side-effecting `GET` endpoints;
- no AX refs, window identity, structured postconditions, or completion state.

Keep it behind an explicit `legacy_pixel` route during migration. Do not put
its mutating GET requests behind generic automatic retry. A timeout after a
click, type, or drag is an unknown-completion state.

Do not hard-code Retina `/2`. The screenshot, display, window, and driver may
use different logical/native coordinate spaces. Pass dimensions and scale
metadata through the response and prefer element refs.

## Validation checklist

1. Mac driver app/host has Accessibility and Screen Recording grants.
2. Daemon restart after any TCC change is verified.
3. Tunnel reaches only the Mac loopback MCP endpoint.
4. Missing/wrong bearer token returns an authentication failure.
5. Browser-origin requests are rejected.
6. `tools/list` and `check_permissions` work through the tunnel.
7. A read-only AX/window state succeeds without changing frontmost app.
8. Background click/type/scroll/drag preserve frontmost app, Space, and real
   cursor where the driver contract promises it.
9. Stale refs are rejected after a fresh snapshot.
10. A transport drop after dispatch does not replay the action.
11. Screenshot and AX-only modes behave correctly when Screen Recording is
    revoked.
12. Daemon restart invalidates old generation/session state.
13. Clipboard reads are approval-gated and do not leak secrets into logs.
14. Prompt injection in a screenshot/page is surfaced and not followed.

Metrics to record: success and false-success rate, p50/p95 action latency,
focus changes, stale-ref refusals, screenshot bytes/tokens, tunnel recovery,
and unknown-completion handling.
