# SerpAPI hosted MCP reference

## Live contract observed

- Official remote endpoint shape: `https://mcp.serpapi.com/<API_KEY>/mcp`.
- Hermes can keep the key out of YAML by using an interpolated path segment, for example:

  ```yaml
  mcp_servers:
    serpapi:
      url: "https://mcp.serpapi.com/${MCP_SERPAPI_API_KEY}/mcp"
      enabled: true
  ```

- The endpoint accepted the MCP `initialize` request without an `Authorization` header. Adding `Authorization: Bearer <same key>` produced HTTP 404, so do not select Hermes' header-auth flow for this path-authenticated endpoint.
- The live endpoint behaved statelessly: `initialize` succeeded but no `MCP-Session-Id` was returned. Subsequent `tools/list` and `tools/call` requests worked without a session header.

## Hermes onboarding sequence

```text
hermes mcp add serpapi --url 'https://mcp.serpapi.com/${MCP_SERPAPI_API_KEY}/mcp'
# At the auth prompt: answer n; the key is already in the URL path.
# At the tool prompt: select only the required tools, or all three when explicitly wanted.
hermes mcp test serpapi
hermes mcp list
hermes tools list
```

A successful live discovery reported three tools:

- `search`
- `search_table`
- `search_dashboard`

Hermes saved the server enabled after discovery and reported that a new session is needed for the tools to enter the agent tool list.

## Schema warning

The `search` wrapper's top-level input schema exposed `mode` and `params`, not top-level `query` and `engine`. A direct call using provider-documentation-style `query`/`engine` arguments returned Pydantic validation errors for unexpected keywords. Always inspect the nested `params` schema and construct the wrapper call from the live schema; do not copy an example blindly.

## Safe verification

Discovery is not enough. After inspecting the nested schema, issue one minimal, non-sensitive search through `tools/call`, check `isError` and returned content, and ensure the credential is absent from logs and output. If the nested schema is unavailable or ambiguous, report that as the remaining blocker instead of guessing.
