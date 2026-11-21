# Design Arena — Code / Preference vs Price pitfall

Session lesson: do not treat “Design Arena” as one benchmark family. The site exposes different slices by category and view; `design_quality` / `judge_score_*` data can contradict the `Code → Preference vs Price` view.

## Correct interpretation

- `design_quality` / `judge_score_*` signals can rank models like `claude-fable-5` highly.
- `Code → Preference vs Price` is a distinct product/coding affordability signal; in the observed session, the user's live Design Arena view showed `glm-5-2` leading with Elo around 1360.
- Never answer “Design Arena ranking” without stating category + view + metric.

## Required data shape

Persist Design Arena rows with explicit dimensions:

- `source = designarena`
- `category` such as `code`, `design_quality`, `fullstack`, etc.
- `view` such as `preference_vs_price`, `elo_rating`, `win_rate`, etc.
- `metric` such as `elo`, `preference_score`, `price_adjusted_score`, `judge_score_*`
- `raw_payload` preserving the original site payload/DOM extraction evidence.

## Analysis rule

Before creating `router_scores` or recommendations:

1. Filter by exact `category` and `view` requested by Monsieur.
2. Normalize only within the same metric family.
3. Refuse/flag mixed slices instead of averaging `judge_score_*` with price-adjusted code preference.
4. If the DB lacks the requested category/view, query Design Arena directly via Camoufox/browser extraction before concluding.

## Ingestion improvement target

The loop should prioritize a dedicated extractor for `Code → Preference vs Price` rather than relying only on `/api/leaderboard/judge-scores`, because that endpoint may not represent the user's visible leaderboard slice.