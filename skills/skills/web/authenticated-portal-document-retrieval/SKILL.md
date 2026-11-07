---
name: authenticated-portal-document-retrieval
category: devops
description: Retrieve and validate documents from authenticated web portals, including Cloudflare-protected login flows, OTP verification, SPA document tables, and signed-download delivery.
---

# Authenticated Portal Document Retrieval

Use this skill when Monsieur asks to recover, inspect, or download documents from a customer, registrar, banking, legal, or other authenticated web portal.

## Core principles

- Treat the portal as the source of truth; never infer a document, account feature, fax number, or identifier from context alone.
- Keep credentials, OTPs, cookies, signed URLs, and vault session material out of chat output and logs.
- An OTP is a login step, not evidence that the documents were retrieved. Continue until the actual file bytes are downloaded and validated.
- Report only artifacts that were physically written and checked. A visible row or a clicked Download button is not a completed retrieval.

## Workflow

0. **Pre-flight: verify network reachability BEFORE any cookie work.** Some government portals geo-block at the TCP level — `assure.ameli.fr` (French health insurance) refuses connections from non-French IPs even though `ameli.fr` resolves. If you cannot `curl` the portal from the target egress, cookies are worthless. Test:

```bash
curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://<portal>/   # 000 = unreachable
curl -sv --max-time 12 https://<portal>/ -o /dev/null 2>&1 | tail -25    # "Connection refused" = geo-block
curl -s --max-time 8 ifconfig.me                                          # confirm egress IP
```

A site that resolves via DNS but refuses TCP from every available egress (Thailand Mac, SG VPS, container) is geo-blocking — stop and report the constraint with unblock options instead of hammering. Full Ameli diagnosis, cookie structure, and unblock paths: `references/ameli-fr-access.md`.

1. **Discover the authentication state**
   - Open the requested portal using the normal authenticated-browser path.
   - Determine whether the session is already authenticated, is asking for credentials, or is blocked by a browser-security interstitial.
   - Avoid repeated credential submissions against an unchanged challenge page.

2. **Use the appropriate browser tier**
   - Prefer the native browser controls first.
   - If a headless session remains on an automatic Cloudflare verification page, switch to a real headed Chromium session on the available desktop display, using a separate temporary browser profile and CDP connection.
   - Wait for the redirect to the portal's real identity-provider page. That redirect, not the end of a timer, is the signal that the challenge has cleared.

3. **Complete authentication safely**
   - Resolve the username and password from the vault or password manager without printing them.
   - Submit the form and wait for the site to generate a fresh one-time code.
   - Ask Monsieur for the code only at that point. Never reuse an OTP from an earlier browser attempt or assume a submitted code was accepted.
   - After submitting the code, wait for the authenticated SPA to finish loading and confirm the account/entity shown on screen.

4. **Locate the correct documents**
   - Inspect the table headers, entity/company name, jurisdiction, document type, received date, status, and lock state.
   - Prefer stable DOM attributes or verified row metadata over positional guesses. If row indexes are used for a short table, re-check the visible document type after opening each row.
   - Distinguish "document listed" from "document downloaded".

5. **Download and validate each artifact**
   - Open the document details view and trigger the portal's own Download action.
   - Capture the download event and keep any signed URL in process memory only.
   - If the browser is containerized and its temporary download path is not visible to the host process, fetch the captured signed URL from the host-side process rather than claiming success from an inaccessible path.
   - Verify HTTP success, the expected content type, non-zero size, and the file signature. For PDFs, use a file/PDF validator and check page count when useful.
   - Repeat validation separately for every document before packaging them.

6. **Deliver precisely**
   - Provide the actual file attachments or absolute paths produced by the run.
   - A ZIP is useful for convenience, but retain the individual files as well.
   - If Monsieur mentions a related service such as a fax dropbox, inspect the portal for it separately and report only an explicitly labeled service. Do not equate an ordinary phone line with a fax service.

## OTP and challenge pitfalls

- A code accepted by one browser session may be invalid or irrelevant to a later session; request a new code after the new session reaches the code screen.
- OTP is issued PER LOGIN SESSION: logging in again mints a new code and the old email's code is rejected, and every fresh login burns a send-quota slot. When sends are exhausted the portal refuses with a "maximum d'envois autorisés atteint"-style error (impots.gouv.fr) or similar — stop hammering, wait for the quota to reset, and do login → read-fresh-OTP → submit in ONE running session. Validated impots.gouv.fr flow (exact field names, OTP semantics, quota) is in `references/impots-gouv-fr-auth.md`.
- Cloudflare's "Performing security verification" page can be an automatic loop. Switching from headless to headed Chromium is the practical escalation; do not endlessly retry the same headless page.
- A login redirect followed by an empty SPA is still an intermediate state. Wait for the table's loading indicator to resolve before extracting rows.
- A Playwright download event can fire even when the browser-local temporary file cannot be read from the host. Validate bytes through a host-visible path.

## Monitoring an authenticated inbox

Use this class when the request is recurring surveillance rather than one-time retrieval: `Received`, `Inbox`, `Documents`, or an equivalent SPA view.

1. Prefer a verified vendor API or inbound webhook when credentials and a public callback already exist. Do not invent a list endpoint from a webhook-only contract.
2. If official API setup would require new credentials or public infrastructure, use the already-authenticated browser session through its local automation API. Acquire cookies from the approved source, resolve key material through the vault, and keep decrypted cookie values in memory only.
3. Navigate directly to the verified inbox URL, wait for the SPA, and evaluate structured page evidence (`href`, title, body, row text, stable links/IDs). Do not treat a screenshot or a positional click as proof of the inbox contents.
4. Handle explicit empty-state text before parsing table-like nodes. Search/filter controls can be exposed as fake rows; filter them out rather than baselining them as documents.
5. Keep an atomic, profile-local state file containing only stable item fingerprints and timestamps. First successful run creates a baseline without alerting; a confirmed empty inbox creates an empty baseline; a blank or partially loaded page must not erase a previous baseline.
6. For daily checks, use a script-only cron job with zero stdout on no-change. Route delivery to a gateway-connected target such as `telegram:<chat_id>`; `origin` may be local-only from Desktop/TUI. Run the job once and verify its status, next run, state file, and local log before reporting success.

The reusable procedure and verified Dropbox Fax/HelloFax SPA details are in `references/silent-inbox-monitoring.md`.

## Completion checklist

- [ ] Authenticated SPA reached.
- [ ] Correct account/entity confirmed.
- [ ] Expected document rows confirmed.
- [ ] Every requested file downloaded to a host-visible path.
- [ ] Every file has non-zero bytes and the expected signature/content type.
- [ ] Attachments/paths delivered, not merely described.
- [ ] Related account features reported separately from verified documents.
- [ ] For recurring monitoring: baseline, empty-state handling, anti-duplicate state, cron delivery target, and one real execution verified.
