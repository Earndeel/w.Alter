# Meta Ads MCP Server (Official)

**URL:** `https://mcp.facebook.com/ads`
**Announced:** April 2026 by Meta
**Help page:** https://www.facebook.com/business/help/1456422242197840
**Developer blog:** https://developers.facebook.com/blog/post/2026/04/29/introducing-ads-cli

## Auth Requirements

- Bearer token auth (NOT OAuth dynamic registration — Meta blocks it)
- Token: Meta User Access Token or System User Token from Graph API
- Scopes: `ads_management`, `ads_read`, `catalog_management`, `business_management`, `pages_show_list`
- Token source: https://developers.facebook.com/tools/explorer/ (select scopes, generate token)
- For long-lived tokens: exchange via `/oauth/access_token` endpoint

## Resource Metadata

```json
{
  "resource": "https://mcp.facebook.com/ads",
  "authorization_servers": ["https://mcp.facebook.com/ads"],
  "scopes_supported": ["ads_management", "ads_read", "catalog_management", "business_management", "pages_show_list"],
  "bearer_methods_supported": ["header"]
}
```

## Capabilities

- Campaign reporting and insights
- Ad creation and management (ads, ad sets, campaigns)
- Catalogue creation and management
- Signal diagnostics (signal health/quality)
- Meta Business Help Centre search

## Config

```yaml
mcp_servers:
  meta-ads:
    url: https://mcp.facebook.com/ads
    headers:
      Authorization: "Bearer <META_ACCESS_TOKEN>"
    timeout: 180
    connect_timeout: 30
```

## Supported AI Agents (Official)

- ChatGPT (via developer mode)
- Claude (via custom connectors / remote MCP)
- Perplexity (via custom remote connectors)

## Pitfalls

- **Dynamic OAuth registration fails** with `400 invalid_client_metadata`. Must use Bearer token.
- **401** = no token provided; **403** = invalid/expired token (different from typical APIs).
- Token must have the right scopes AND the user must have access to the ad account.
- Tools are prefixed `mcp_meta_ads_*` in Hermes.

## Alternative: Pipeboard (Community)

If Meta's official MCP doesn't work, `pipeboard-co/meta-ads-mcp` (904⭐) is the community alternative:
- Remote: `https://mcp.pipeboard.co/meta-ads-mcp`
- CLI: `brew install pipeboard-co/tap/pipeboard`
- Also covers Google Ads + TikTok Ads
