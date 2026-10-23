# Meta Ads MCP — Auth & Connection Reference

## Official Server
- URL: `https://mcp.facebook.com/ads`
- Type: Remote HTTP (StreamableHTTP)
- Announced: April 2026, Meta Business Help Centre
- Help page: https://www.facebook.com/business/help/1456422242197840
- Developer blog: https://developers.facebook.com/blog/post/2026/04/29/introducing-ads-cli

## Auth: Bearer Token (NOT OAuth MCP Dynamic Registration)
Meta's MCP server does **NOT** support MCP dynamic client registration. Attempting it returns:
```json
{"error":"invalid_client_metadata","error_description":"Dynamic registration is not available for this client."}
```

The server accepts standard **Bearer tokens** (Meta Marketing API access tokens).

### How to discover auth requirements
1. POST to the MCP URL with no auth → 401
2. Read the `WWW-Authenticate` header:
   ```
   Bearer resource_metadata="https://mcp.facebook.com/.well-known/oauth-protected-resource/ads", scope="ads_management ads_read catalog_management business_management pages_show_list"
   ```
3. GET the resource metadata URL → reveals authorization servers and supported scopes
4. The server accepts `Authorization: Bearer <token>` with a valid Meta access token

### Required Scopes
- `ads_management` — create/edit/delete campaigns, ad sets, ads
- `ads_read` — read campaign data and insights
- `catalog_management` — product catalogue operations
- `business_management` — business account access
- `pages_show_list` — list Facebook pages for ad creatives

### How to Get a Token
1. Go to https://developers.facebook.com/tools/explorer/
2. Select your Meta app (or use the default "Graph API Explorer" app)
3. Click "Generate Access Token"
4. Select the required scopes above
5. Copy the token (short-lived ~1h; extend via token debugger)

For long-lived tokens: exchange short-lived token via `/oauth/access_token` endpoint.

### MCP Config
```yaml
mcp_servers:
  meta-ads:
    url: https://mcp.facebook.com/ads
    timeout: 180
    connect_timeout: 30
    headers:
      Authorization: "Bearer <YOUR_META_ACCESS_TOKEN>"
```

## Available Tools (mcp_meta_ads_*)
- `get_ad_accounts` — list accessible ad accounts
- `get_account_info` — account details
- `get_campaigns` / `get_campaign_details` / `create_campaign`
- `get_adsets` / `get_adset_details` / `create_adset` / `update_adset`
- `get_ads` / `get_ad_details` / `create_ad` / `update_ad`
- `get_ad_creatives` / `create_ad_creative` / `update_ad_creative`
- `upload_ad_image` / `get_ad_image`
- `get_insights` — performance metrics with breakdowns (age, gender, country)
- `search_interests` / `get_interest_suggestions` / `validate_interests`
- `search_behaviors` / `search_demographics` / `search_geo_locations`
- `create_budget_schedule`
- `get_login_link` — OAuth login for interactive auth
- `search` — generic search across accounts, campaigns, ads, pages

### Campaign Objectives (ODAX)
Legacy objectives (BRAND_AWARENESS, LINK_CLICKS, etc.) are **deprecated**. Use:
- `OUTCOME_AWARENESS`
- `OUTCOME_TRAFFIC`
- `OUTCOME_ENGAGEMENT`
- `OUTCOME_LEADS`
- `OUTCOME_SALES`
- `OUTCOME_APP_PROMOTION`

## TikTok Ads MCP (Pipeboard, not official)
- URL: `https://mcp.pipeboard.co/tiktok-ads-mcp`
- Auth: Bearer token from https://pipeboard.co/settings
- No official TikTok MCP exists as of May 2026

## Pitfalls
- Dynamic OAuth registration is NOT supported — must use Bearer token
- Tokens from Graph API Explorer are short-lived (~1h) — use long-lived for production
- Old campaign objectives (BRAND_AWARENESS, LINK_CLICKS, etc.) return 400 — use ODAX outcomes
- The server returns 403 (not 401) when a token is present but invalid
