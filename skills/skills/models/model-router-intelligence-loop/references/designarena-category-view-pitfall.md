# Design Arena category/view pitfall

## What happened
During a Design Arena analysis, the local DB contained `source='designarena'` rows for `judge_score_*` metrics under a design-quality style category. The user was looking at the UI view **Code → Preference vs Price** and correctly flagged that the ranking did not match.

## Lesson
Do not treat “Design Arena” as a single benchmark. Its rankings depend on at least:

- category, e.g. `Code`, design/fullstack/product categories
- view, e.g. `Preference vs Price`, `Elo Rating`, `Win Rate`, raw judge-score views
- metric family, e.g. `judge_score_*` vs price-adjusted preference/elo signals

A model can dominate Design Arena judge-score/design-quality metrics while losing on Code → Preference vs Price. These are different decision signals.

## Required analysis pattern
1. Ask/derive the exact Design Arena category and view from the user request.
2. Query the DB for rows matching that category/view/metric family.
3. If only generic `judge_score_*` rows exist, say the DB does **not** contain the requested UI view yet.
4. Fetch or ingest the specific view before ranking, or clearly label the analysis as limited to the available metric family.
5. Never present a source-level Design Arena winner unless the category/view scope is explicit.

## Reporting template
- Scope: `Design Arena / <category> / <view>`
- Coverage: model count, metric count, last observed timestamp
- Winner(s): by the requested metric only
- Caveat: note missing views/categories separately, not as part of the ranking
