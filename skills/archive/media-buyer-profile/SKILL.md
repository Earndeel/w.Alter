---
name: media-buyer-profile
category: devops
description: "Autonomous media buyer agent profile — Meta Ads + TikTok Ads campaign management via MCP. Analysis, creation, optimization, scaling."
tags: [media-buyer, meta-ads, tiktok-ads, mcp, advertising, campaign-management]
---

# Media Buyer Profile

## Purpose
Dedicated Hermes profile for autonomous advertising campaign management on Meta (Facebook/Instagram) and TikTok via MCP servers.

## Architecture
- `default` profile = W.Alter (orchestrator, user interaction)
- `media-buyer` profile = ad campaign specialist (analysis, creation, optimization, scaling)
- Default model: mimo-v2.5-pro (gitlawb) — same as main orchestrator

## MCP Servers
1. **Meta Ads** (official by Meta): `https://mcp.facebook.com/ads`
   - Auth: Bearer token (Meta Marketing API access token)
   - Scopes: ads_management, ads_read, catalog_management, business_management, pages_show_list
   - Token source: https://developers.facebook.com/tools/explorer/
   - Note: This is the OFFICIAL Meta MCP (launched April 2026), NOT Pipeboard. Meta's MCP does NOT support OAuth dynamic client registration — a pre-obtained Meta access token is required as Bearer header.
   - Blog: https://developers.facebook.com/blog/post/2026/04/29/introducing-ads-cli
   - Help: https://www.facebook.com/business/help/1456422242197840

2. **TikTok Ads** (Pipeboard — deferred): `https://mcp.pipeboard.co/tiktok-ads-mcp`
   - Auth: Bearer token (Pipeboard API token)
   - Token source: https://pipeboard.co/settings
   - Status: Deferred — TikTok MCP is too new, will revisit later
   - Auth: Bearer token (Pipeboard API token)
   - Token source: https://pipeboard.co/settings
   - Status: deferred — Lucas wants to revisit later
   - Token source: https://pipeboard.co/settings
   - Status: Scaffolded but not activated — Lucas wants to revisit later

## How to Invoke
```bash
hermes -p media-buyer chat -Q --source tool -q "Analyse les performances des campagnes Meta des 7 derniers jours"
```

Or via W.Alter delegation:
```bash
hermes -p default chat -Q --source tool -q "Utilise le profil media-buyer pour analyser les campagnes Meta"
```

## Token Setup
Tokens are stored as env vars in `~/.hermes/profiles/media-buyer/.env`:
```
META_ADS_TOKEN=EAAx...
PIPEBOARD_API_TOKEN=pbr_...
```

The MCP config in config.yaml references them via `${META_ADS_TOKEN}` and `${PIPEBOARD_API_TOKEN}`.

## Key MCP Tools Available

### Meta Ads (mcp_meta_ads_*)
- `mcp_meta_ads_get_campaigns` — List campaigns
- `mcp_meta_ads_create_campaign` — Create campaign (objectives: OUTCOME_AWARENESS, OUTCOME_TRAFFIC, OUTCOME_ENGAGEMENT, OUTCOME_LEADS, OUTCOME_SALES, OUTCOME_APP_PROMOTION)
- `mcp_meta_ads_get_insights` — Performance metrics with breakdowns
- `mcp_meta_ads_get_adsets` / `mcp_meta_ads_create_adset` — Ad set management
- `mcp_meta_ads_get_ads` / `mcp_meta_ads_create_ad` — Ad management
- `mcp_meta_ads_search_interests` — Interest targeting research
- `mcp_meta_ads_search_geo_locations` — Location targeting

### TikTok Ads (mcp_tiktok_ads_*)
- Tools discovered at runtime from Pipeboard MCP

## References
- `references/meta-ads-mcp-auth.md` — Meta Ads MCP auth flow, token setup, tool catalog, pitfalls

## Safety Rules
- All creations default to PAUSED status
- Never delete without explicit user confirmation
- Always show budget totals before execution
- Data-first: always fetch metrics before making recommendations

## References
- `references/meta-mcp-auth.md` — OAuth discovery notes, token acquisition, supported agents
