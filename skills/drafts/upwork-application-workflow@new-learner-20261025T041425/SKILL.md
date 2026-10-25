---
name: upwork-application-workflow
description: Use when selecting Upwork missions, preparing tailored proposals, or submitting applications while respecting spending limits.
---

## Establish authorization and spending limits

Treat permission to submit proposals separately from permission to spend. Record the current spending constraint. If spending is forbidden, do not purchase Connects, activate subscriptions, or boost proposals. Continue investigating free opportunities without assuming they exist.

## Authenticate and inspect the live account

1. Call `browser_session(site="upwork", session="<session>", verify=true)` through the Walter MCP server. Use its returned session identifier; never extract cookies.
2. Open a tab with `walter-browser -s <session> new apply`.
3. Navigate with `walter-browser -s <session> nav '<url>'`.
4. Inspect the loaded page with `walter-browser -s <session> eval '({title:document.title,path:location.pathname,text:document.body?.innerText?.slice(0,18000)})'`.
5. If navigation returns before the application loads, inspect again after completion. An empty or intermediate page is not evidence of account status. If an old session no longer authenticates, provision a verified browser session again.

## Find and qualify missions

Search relevant categories, for example `/nx/search/jobs/?q=AI%20video&sort=recency`. Extract structured cards:

```javascript
[...document.querySelectorAll("article")].map(x=>({
  title:x.querySelector("h2,h3")?.innerText,
  uid:x.getAttribute("data-ev-job-uid"),
  text:x.innerText,
  links:[...x.querySelectorAll("a")].map(a=>({
    title:a.innerText,url:a.getAttribute("href")
  }))
}))
```

Inspect the individual listing before preparing a proposal. Check deliverables, budget, client history, competition, required skills, and available evidence of relevant work. Exclude requirements the applicant cannot substantiate. For fixed-price work, clarify quantity, duration, revisions, and production costs before assuming profitability.

Search-card titles and links may be insufficient; inspect `data-ev-job-uid` and verify the resulting listing or application page. Do not assume the browser CLI's stdout is raw JSON: inspect its response format before parsing it with `json.loads`.

## Inspect the application gate before submission

Open the listing's application form; the observed route is `/nx/proposals/job/~<job-uid>/apply/`. Verify the actual page rather than relying on the route alone.

Read the live Connect balance, Connect requirement, proposal fields, and any charges. A prepared cover letter does not bypass Connect requirements. If the balance is insufficient and spending is forbidden, mark that application blocked and retain its draft. Check invitations or other free routes individually; do not promise free submission without verifying the form.

## Prepare, submit, and report accurately

Tailor each proposal to the listing, use only verified portfolio claims, and set an explicit scope and price. Keep a ledger containing the listing URL, proposed terms, Connect requirement, draft, and status. Leave boosts disabled unless authorized.

Submit only when authorization and the live account permit it. Confirm success through the resulting page or proposal history. Distinguish prepared, blocked, and submitted applications in every report; never count drafts as submissions.
