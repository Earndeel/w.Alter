# Meta Ads MCP — OAuth & Auth Notes

## Official Endpoint
`https://mcp.facebook.com/ads`

## Auth Mechanism
- Requires Bearer token (Meta Marketing API access token)
- Does NOT support MCP OAuth dynamic client registration (returns 400 `invalid_client_metadata`)
- OAuth Protected Resource Metadata (RFC 9728) available at:
  `https://mcp.facebook.com/.well-known/oauth-protected-resource/ads`

## Resource Metadata (discovered)
```json
{
  "resource": "https://mcp.facebook.com/ads",
  "authorization_servers": ["https://mcp.facebook.com/ads"],
  "scopes_supported": ["ads_management", "ads_read", "catalog_management", "business_management", "pages_show_list"],
  "bearer_methods_supported": ["header"]
}
```

## How to Get a Token
1. Go to https://developers.facebook.com/tools/explorer/
2. Select your Meta app (or create one)
3. Generate a User Access Token with scopes: ads_management, ads_read, catalog_management, business_management, pages_show_list
4. For long-lived tokens, exchange via `/oauth/access_token` endpoint

## Supported AI Agents (official)
- ChatGPT (via developer mode)
- Claude (via custom connectors at claude.ai/settings/integrations)
- Perplexity (via custom remote connectors)
- Any MCP client with Bearer token auth

## CLI Alternative
Meta also launched an Ads CLI: https://developers.facebook.com/blog/post/2026/04/29/introducing-ads-cli
Docs: https://developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-cli/ads-cli-overview
