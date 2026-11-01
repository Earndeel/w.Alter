# Archived source routing: blocked-page-recovery

The specialized `blocked-page-recovery` procedure is consolidated into `agentic-web-navigation` as its blocked-page recovery branch. The original skill package must remain intact when archived at `.archive/blocked-page-recovery`; no script is flattened into this umbrella.

## Use the surviving umbrella

For current work, load `agentic-web-navigation`. On a `403/429`, paywall, WAF, or bot interstitial, stop retrying the same URL and use its recovery ladder: Wayback, archive.today host rotation, Jina Reader only with `JINA_API_KEY`, a same-host API/GraphQL/RSS/sitemap pivot, then an interactive browser. Validate the response body, distinguish `snapshot` from `live`, and never send cookies or Authorization headers through a generic proxy relay.

## Exact historical procedure

After the archive is present, refresh `skills_list` and confirm that the actual archive location is `.archive/blocked-page-recovery`. Do not retry the old unqualified name. Load the original package and its exact implementation with:

```text
skill_view(name='.archive/blocked-page-recovery')
skill_view(name='.archive/blocked-page-recovery', file_path='scripts/recover_page.py')
```

The archived `SKILL.md` preserves the full ladder and provenance rules; `scripts/recover_page.py` preserves the complete stdlib implementation and its body-validation heuristics. Re-verify historical routes against current responses before relying on them.
