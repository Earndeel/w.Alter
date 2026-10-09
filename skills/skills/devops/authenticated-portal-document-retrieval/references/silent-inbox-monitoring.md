# Silent authenticated-inbox monitoring

## When to use
Use this pattern when a portal exposes a `Received`, `Inbox`, `Documents`, or equivalent SPA view and Monsieur wants a recurring alert only when a new item appears.

## Preferred transport
1. Prefer the vendor's official API or inbound webhook when credentials and a public callback endpoint are already available.
2. Do not invent a list endpoint from a webhook-only API. Verify the vendor contract first.
3. If the official API requires new credentials or public infrastructure, use the existing authenticated browser session through its local automation API rather than adding a public proxy for a small monitoring job.

## Browser-API polling pattern
- Acquire an authenticated session from the approved cookie source; resolve key material from the vault and keep decrypted values in memory only.
- Inject cookies into a fresh browser context/session for each poll.
- Navigate directly to the portal's verified inbox URL and wait for the SPA to finish loading.
- Use a page-evaluation call to return structured evidence (`href`, title, body text, row text, stable links/IDs). Avoid relying on a positional click or a screenshot alone.
- Recognize explicit empty-state text such as `No faxes yet` before interpreting table-like elements. Search/filter controls can appear as fake rows (for example, a row containing only `SEARCH`).
- Close the tab in a `finally` block.

## Idempotent alert state
- Store only stable item fingerprints and timestamps in a profile-local state file, for example `HERMES_HOME/state/<portal>-received.json`.
- Hash the stable row identifier/link plus normalized row text; do not persist cookies, signed URLs, or document contents.
- First successful run creates a baseline and emits no alert.
- A confirmed empty inbox sets an empty baseline. A blank or partially loaded page must not erase a previous non-empty baseline.
- Atomically replace the state file after a successful parse.
- Produce no stdout when there is no new item. Write diagnostics to a local log instead; stdout is the notification payload for script-only cron.

## Cron delivery
- Use a script-only cron job (`no_agent: true`) for deterministic polling and zero LLM cost.
- The script should return success with no output for no-change and transient failures when the user's contract is “notify only on new items”; retain diagnostics locally.
- Use a gateway-connected target such as `telegram:<chat_id>` for delivery. `origin` can be local-only when the creating session is Desktop/TUI and has no live delivery channel.
- Run the script once immediately after creation and verify the job's `last_status`, next run, state file, and log. Do not claim monitoring is active from a cron creation response alone.

## Failure boundaries
- Authentication expiry, unavailable browser backend, or an empty/partial SPA response must not create a false “new document” alert.
- If a session source depends on a separate desktop browser, record that operational dependency in the local log; never print cookie material or account secrets.
- If the vendor later supplies official API credentials and a public callback, migrate to the webhook/API path and keep the same idempotency and delivery contract.

See this file's companion procedure for the verified SPA/API and state-machine details used during a Dropbox Fax/HelloFax inbox monitor: `references/silent-inbox-monitoring.md`.
