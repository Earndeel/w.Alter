---
name: remote-mcp-provider-onboarding
description: Use when onboarding a hosted HTTP MCP provider safely.
version: 1.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [mcp, remote, http, streamable-http, auth, schema, providers]
---

# Remote MCP provider onboarding

## Trigger

Use this skill when connecting Hermes to a hosted MCP provider over HTTP, especially when the provider puts a credential in the endpoint URL, exposes provider-specific tool schemas, or fails during MCP discovery.

This complements the general `native-mcp` and `mcporter` skills: those explain MCP clients and transports; this skill governs provider onboarding, secret placement, authentication diagnosis, schema discovery, and end-to-end verification.

## Operating rules

- Treat the provider's official MCP documentation as authoritative for endpoint shape and authentication. Do not infer auth from the fact that a URL contains a token.
- Keep raw credentials out of shell arguments, config files, skill files, logs, transcripts, and final reports. Prefer Hermes' secret source/broker; use the profile `.env` only for credentials when that is the configured local mechanism, with restrictive permissions.
- Use environment interpolation in Hermes config (`${VAR}` or `${env:VAR}`) so the YAML stores a reference rather than the credential.
- Do not call a discovered tool from marketing examples until `tools/list` (or Hermes discovery output) has been checked. Provider examples often use a different schema than the MCP wrapper.
- Prefer the narrowest tool whitelist that satisfies the task. Enable all tools only when the provider's surface is small, understood, and explicitly wanted.

## Procedure

### 1. Establish the provider contract

Record, without copying any secret:

- Official MCP endpoint and transport (Streamable HTTP, SSE, or stdio).
- Where the credential belongs: URL path, query parameter, header, OAuth flow, or provider-specific environment variable.
- Whether the server is stateful. Some hosted endpoints legitimately omit `MCP-Session-Id` and accept independent JSON-RPC requests.
- Tool names and the input schema returned by discovery.

If the endpoint or auth contract is ambiguous, perform a documentation lookup before changing Hermes config.

### 2. Place the credential safely

Use a provider-specific environment name such as `MCP_<PROVIDER>_API_KEY` and store only the value in the configured secret source. Never print it to verify presence; verify only a boolean or a redacted identifier. Preserve file mode `0600` when `.env` is used.

Do not put a real credential in:

- `config.yaml`;
- an MCP URL passed literally on a command line;
- a skill, template, test fixture, or support file;
- a tool result or completion message.

### 3. Configure the URL with interpolation

Use the smallest Hermes entry that reflects the provider contract:

```yaml
mcp_servers:
  provider_name:
    url: "https://provider.example/mcp/${MCP_PROVIDER_API_KEY}"
    enabled: true
```

For a header-authenticated provider, use the provider's documented header and an interpolated value. Do not add an `Authorization` header merely because it is conventional; a path-authenticated endpoint may reject it.

Use `hermes mcp add` when it can represent the provider correctly. If its interactive auth prompt would add an incompatible header, answer that the server does not require header authentication and retain the interpolated URL instead. Whitelist tools during the same operation when appropriate.

### 4. Diagnose discovery failures systematically

If `hermes mcp add` or `hermes mcp test` reports a terminated session:

1. Confirm the interpolated URL is resolved without printing it.
2. Compare the provider's documented auth mode with the headers Hermes is sending.
3. Probe the MCP `initialize` request with and without the disputed auth header, redacting the credential in all exceptions.
4. Check status code, content type, and whether the response is valid JSON-RPC.
5. Do not permanently disable the server or switch transports until the mismatch is identified.

A successful `initialize` without a session header is not automatically a failure; test the provider's stateless `tools/list` behavior before adding client-side session assumptions.

### 5. Discover before invoking

Run:

```text
hermes mcp test <name>
hermes mcp list
hermes tools list
```

Capture only server name, transport, auth mode, tool count, and tool names. Inspect the full `inputSchema` for the intended tool. Nested wrapper fields such as `mode` and `params` are common; do not pass top-level `query`, `engine`, or similar arguments unless the discovered schema explicitly accepts them.

### 6. Verify a real call

After discovery succeeds, make one minimal, low-cost, non-sensitive call through the actual MCP tool. Validate:

- JSON-RPC success and no `isError` result;
- returned content is structurally consistent with the schema;
- the provider-specific operation actually ran, not merely `initialize`/`tools/list`;
- the secret did not appear in the output, logs, or error text.

If the wrapper schema is unclear, stop at discovery and inspect the nested schema rather than guessing arguments.

### 7. Activate safely

MCP tool exposure is normally fixed when an agent session builds its tool list. After configuration changes, start a new Hermes session (or use `/reload-mcp` where supported). Report the exact verification result and any provider-specific caveat; do not claim current-session availability merely because the config was saved.

## Pitfalls

- **Credential in the URL plus `--auth header`:** can cause a provider to return 404 or terminate the session. Use the documented path credential alone when that is the contract.
- **Assuming every server returns `MCP-Session-Id`:** hosted stateless servers may not. Test subsequent JSON-RPC calls without a session header.
- **Using examples instead of the discovered schema:** MCP wrappers may expose `mode`/`params` while provider docs show `query`/`engine` at the top level.
- **Testing only discovery:** a connected server with three tools is not proof that a search or generation call works. Execute one safe real call when the schema is unambiguous.
- **Putting secrets in support artifacts:** references may record endpoint shapes and quirks, never real keys or copied authenticated URLs.

## Verification checklist

- [ ] Official endpoint/auth contract confirmed.
- [ ] Credential stored through the configured secret mechanism and never printed.
- [ ] Config uses `${...}` interpolation, not a raw key.
- [ ] `hermes mcp test <name>` connects.
- [ ] Tool count and names are discovered from the live server.
- [ ] Intended tool's nested `inputSchema` has been inspected.
- [ ] One safe real call succeeds, or the remaining blocker is stated precisely.
- [ ] New session/reload requirement is reported.

## Support reference

- `references/serpapi-mcp.md` — provider-specific endpoint, auth, statelessness, discovery, and schema lessons captured from a live onboarding.