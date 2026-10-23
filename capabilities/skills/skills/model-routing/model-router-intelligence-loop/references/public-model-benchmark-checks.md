---
name: public-model-benchmark-checks
description: Quick verification workflow for checking a single AI model across public benchmark sources such as Artificial Analysis, Design Arena, and launch announcements.
---

# Public Model Benchmark Checks

Use this when Monsieur asks to "checker" a model by name, especially when he mentions Artificial Analysis, Design Arena, benchmark ranking, cost/performance, or whether a new model is worth testing.

## Workflow

1. Search the exact model name first, quoted when useful.
2. Check Artificial Analysis in two places:
   - `site:artificialanalysis.ai <model>`
   - `site:artificialanalysis.ai/articles "<model>"`
   - the model page if a slug exists, e.g. `/models/<model-slug>`.
3. Check Design Arena separately:
   - `"<model>" "Design Arena"`
   - `"<model>" "DesignArena"`
   - `site:x.com/Designarena "<model>"`
4. If a page is a SPA or extraction is thin, use browser/navigation or search snippets as corroboration, but label exactly what was verified from which source.
5. Report source-specific standing, not universal truth. Example: "#1 on Design Arena" is not the same as "best model overall".
6. Final answer should be terse: Artificial Analysis result, Design Arena result/Elo if found, source URLs in plain text or backticks, and a practical conclusion.

## Pitfalls

- Do not silently convert a benchmark claim into a general quality claim.
- Do not invent pricing, scores, or ranks when the page extraction does not expose them.
- For Monsieur, URLs must be plain text or backticked, never markdown links.
- "Checker" means cookies/scrape/public verification where possible, not assuming an API is available.

## References

- `references/glm-5-2-check.md` — example quick-check pattern and source set for GLM-5.2.
