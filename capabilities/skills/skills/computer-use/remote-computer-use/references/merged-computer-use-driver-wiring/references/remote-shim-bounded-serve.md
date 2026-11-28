# Remote shim bounded-serve contract

## Why this reference exists

The generic driver-wiring skill must teach the contract, not preserve a
one-session error narrative. This reference records the reusable validation and
verification pattern for a remote `cua-driver` stdio shim used by Hermes.

## Exact Hermes unrestricted argv

Hermes' private embedded path invokes:

```text
<driver> serve --embedded --socket /tmp/hc-<token>.sock \
  --no-permissions-gate --permission-mode unrestricted \
  --dangerously-bypass-approvals
```

A compatible remote shim forwards this bounded argv to the enrolled GUI host,
where the daemon owns the socket. The shim must validate locally before SSH:

- verb is exactly `serve`;
- required flags appear exactly once;
- `--socket` has one safe absolute path, with no shell metacharacters or control
  characters;
- permission mode is exactly `unrestricted`;
- no unknown flags or extra positional arguments are accepted.

For `status` and `stop`, accept either no arguments or exactly
`--socket <validated-path>`. Keep all other verbs independently bounded.

## Manifest invariant

The remote host's manifest can contain its absolute Mac executable path. Rewrite
only the MCP invocation command to empty while retaining validated args, for
example:

```json
{"mcp_invocation":{"command":"","args":["mcp"]}}
```

Hermes then keeps the already-resolved local shim and never tries to execute the
Mac path on the VPS.

## Verification sequence

1. Run the exact `serve` argv against the shim's local validator; confirm it is
   accepted without opening SSH.
2. Test malformed/unknown/duplicate flags and unsafe socket paths; confirm
   fail-closed rejection.
3. Run the shim's complete contract tests.
4. Run the Hermes backend/plugin tests for both `standard` and `unrestricted`.
5. Start the real unrestricted route, poll `status`, exercise a read-only
   window listing, then stop it cleanly.
6. Keep target-side GUI/TCC evidence separate: a green shim test proves only
   transport/argv compatibility, not Accessibility, Screen Recording, or a
   usable unlocked Mac session.

## Important correction

Do not fix a remote-shim incompatibility by silently coercing the plugin factory
from `unrestricted` to `standard`. That changes the user's explicit approval
semantics. Either implement the exact bounded remote contract or report a clear
compatibility blocker.
