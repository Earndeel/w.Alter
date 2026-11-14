# Interactive local panel smoke

Use this recipe when a local HTML artifact is backed by a small API and runs work asynchronously (extractors, crawlers, fixture matrices, test labs).

## Contract to expose

Prefer a local API with these observable states:

- `GET /api/health` — engine readiness and capability flags;
- `GET /api/scenarios` — the scenario matrix the UI renders;
- `POST /api/runs` — returns a run id immediately with `queued` state;
- `GET /api/runs/<id>` — transitions through `queued`, `running`, `complete`, or `error` and contains events plus the final result.

Keep fixtures deterministic and run them through the same scorer/projector as the live path. Reserve live network mode for a validated scenario; make the distinction visible in the UI.

## Playwright smoke sequence

```python
await page.goto(panel_url, wait_until="networkidle")
await page.wait_for_selector("#run-all:not([disabled])")
await page.locator("#run-all").click()

# Enqueue completion is not worker completion. Scope the assertion to the run list
# and wait for terminal badges, not merely for the number of queued rows.
await page.wait_for_function(
    "document.querySelectorAll('#run-list .status-pill.success, "
    "#run-list .status-pill.warning').length === expected_count"
)

await page.locator('[data-scenario="flight-search"]').click()
await page.locator("#run-selected").click()
await page.wait_for_function(
    "document.querySelectorAll('#run-list .status-pill.success, "
    "#run-list .status-pill.warning').length === expected_count + 1"
)
await page.locator('[data-tab="records"]').click()
assert await page.locator("table tbody tr").count() >= 1
```

Adapt ids to the artifact. The important invariants are behavioral: the engine becomes ready, the matrix loads, a fixture run reaches a terminal semantic outcome, a rejected/noise fixture is rejected, a valid run exposes normalized records, and no browser console/page errors occur.

## Race and selector pitfalls

- Disable run controls until the scenario and health requests have completed; otherwise a fast automated click can beat bootstrap even though a human never notices.
- A batch button may return after enqueueing workers while polling continues. Wait for terminal `accepted`/`rejected`/`error` states.
- Scope counts to the run-list container. A detail pane may render a second copy of the active run's status badge.
- Use runtime selectors and DOM state, never read source files to assert implementation shape.

## Responsive contract

At desktop and mobile viewports assert:

```python
widths = await page.evaluate(
    "({scrollWidth: document.documentElement.scrollWidth, "
    "clientWidth: document.documentElement.clientWidth})"
)
assert widths["scrollWidth"] == widths["clientWidth"]
```

Also click one scenario and one result tab at the mobile width; a screenshot alone does not prove that the controls remain usable.

## Security baseline for local live probes

If the panel accepts a user-supplied live URL, keep the server local-only, allow only `http`/`https`, reject localhost/private/link-local/reserved targets after DNS resolution, and do not persist cookies, authorization headers, or complete response bodies by default. Return bounded payload previews for inspection.
