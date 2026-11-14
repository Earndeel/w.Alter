# Northwest Registered Agent (NWRA) — Session Notes

## Site Details
- **Main site**: northwestregisteredagent.com
- **Accounts portal**: accounts.northwestregisteredagent.com (SPA, Keycloak SSO)
- **Auth provider**: Keycloak (id.northwestregisteredagent.com)

## Cloudflare Protection
- Protected by Cloudflare Turnstile
- Camoufox passes CF with zero challenge (tested 2026-05-24)
- cf_clearance is fingerprint-bound — NEVER inject from Mac Brave into Camoufox

## Auth Cookies (Keycloak SSO)
Required cookies for authenticated access:
- `KEYCLOAK_IDENTITY`, `KEYCLOAK_IDENTITY_LEGACY` (domain: id.northwestregisteredagent.com)
- `KEYCLOAK_SESSION`, `KEYCLOAK_SESSION_LEGACY` (domain: id.northwestregisteredagent.com)
- `AUTH_SESSION_ID`, `AUTH_SESSION_ID_LEGACY` (domain: id.northwestregisteredagent.com)
- `KEYCLOAK_REMEMBER_ME` (domain: id.northwestregisteredagent.com)
- `PHPSESSID` (domain: www.northwestregisteredagent.com)
- `frontend` (domain: accounts.northwestregisteredagent.com and .northwestregisteredagent.com)
- `_interslice_session` (domain: accounts.northwestregisteredagent.com)

## SPA Behavior
- Accounts portal is a React SPA with hash routing (`#/documents`, `#/services`, `#/businesses`)
- Documents page loads dynamically — wait 8-10s after navigation before snapshot
- Download buttons trigger S3 pre-signed URLs (valid ~5 days / 432000 seconds)
- To capture download URL: use Playwright `expect_download` or intercept network

## Document Download
- Click document row by name (use `selector: "text=Document Name"`, not ref)
- Click Download button on detail page
- S3 URLs are pre-signed and can be downloaded via curl from VPS
- Documents: Formation Document, Operating Agreement, Initial Resolutions

## Account Structure
- Entity: Earndeel LLC, New Mexico (Entity ID: 0008101758)
- Formation date: 05/11/2026
- Registered Agent: Northwest Registered Agent, Inc., 1209 Mountain Road Pl NE Ste N, Albuquerque, NM 87110
- Services: Brand Protection, Business Domain (earndeel.com), Email, Phone, Registered Agent, Website Hosting

## Pitfalls
- SPA navigation: must wait for content to load (8-10s sleep after navigate)
- Table rows have no [eN] refs — use `selector: "text=..."` for clicking
- Session expires after ~5-10 minutes of inactivity — re-inject cookies
- cf_clearance cookie expires — Camoufox gets its own automatically on navigation
- Keycloak SSO session: after cookie injection, navigate to `accounts.northwestregisteredagent.com/#/documents` (not just `/`). If redirected to login page, the Keycloak session is dead — need fresh cookies from Mac Brave
- Document download: S3 URLs captured via Playwright `expect_download` are valid ~5 days (432000s). Can re-use URLs from a previous session without re-navigating
