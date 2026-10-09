# Verified ChatGPT Work usage probe

This field note captures a reusable probe pattern. It deliberately omits the account identity, live balance, reset countdown, cookie values, and all authenticated page content; those are transient or secret.

## Proven sequence

1. Check the active Camoufox-Max health endpoint.
2. Copy the Brave `Cookies` database on the approved Mac host and query only target-domain rows. Decrypt locally with the vault-provided key, filter non-auth/analytics cookies, and write a restrictive temporary JSON file without printing values.
3. Inject with the current host API using an envelope, not a raw array:

```json
{"userId":"temporary-usage-check","cookies":[{"name":"...","value":"...","domain":"chatgpt.com","path":"/"}]}
```

4. Create a temporary tab, navigate explicitly to the product URL, and take a fresh snapshot. A product path such as `/codex` may be a public marketing page rather than the execution UI.
5. In the ChatGPT surface used for the quota, select the visible Work mode and verify the active model from the fresh snapshot before sending anything.
6. Open profile → Settings → Usage. If the semantic snapshot omits progress-bar values, evaluate only the visible dialog's text and filter to usage/limit/credits/reset terms.
7. For a user-authorized calibration run, type one deterministic no-tool prompt and click Send. Wait for the answer to finish; do not use a keyword from the prompt as the completion signal.
8. Reload the page, reopen Usage, and compare the same labeled metric. Report an unchanged displayed metric as unchanged; do not call it zero cost.
9. Delete the temporary session and remove local/remote copied browser databases, cookie JSON, payloads, snapshots, and logs.

## Exact failure lessons

### Cookie wrapper

Sending the raw cookie array to `POST /session/cookies` returned an error equivalent to:

```text
browserContext.addCookies: cookies: expected array, got undefined
```

The server expects `req.body.cookies`, so use `{userId, cookies}` and do not log the payload.

### Ref discovery and re-rendering

The page exposed multiple profile/menu nodes. Clicking the first generic `Open profile menu` ref caused a server error, while the explicitly labeled account/profile control worked. After transitions, refs changed again: Settings and Usage had to be rediscovered from a new snapshot. A click response alone was not treated as proof of a state change; the page was allowed to settle and then snapshotted again.

Practical rule: match the exact visible label first, prefer the newest ref, and if a click returns HTTP 500 capture the current snapshot instead of repeating the stale ref.

### Completion detection

The control prompt contained the expected answer word. A detector that searched for that word reported completion while the UI was still showing `Working`/`Stop answering`. The reliable check is: the answering control disappears, the final assistant message is present, and the result is read from the assistant node—not from the prompt or a generic body substring.

### Metric interpretation

The Usage panel showed a credit balance and a weekly reset statement as separate UI concepts. After one completed Work/model control run and a full reload/reopen of Usage, the displayed credit balance was unchanged. This proves only that the displayed balance did not change in that observation window; it does not prove the run was free or that no included rolling-limit usage occurred.

## Safe reporting contract

Report:

- authenticated account/plan label, if visible and non-sensitive;
- active product surface and model/mode;
- exact baseline and post-run labels;
- completion evidence;
- whether the displayed metric changed;
- the limitation if the UI does not expose marginal cost.

Never report cookies, tokens, email contents, raw snapshots, or account history. Never click reset, buy credits, auto-reload, upgrade, or billing controls during a read-only probe.
