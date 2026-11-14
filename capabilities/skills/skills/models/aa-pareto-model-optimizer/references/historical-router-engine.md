# aa-pareto-model-optimizer — The former router engine, superseded by Walter Router (history).

Moved verbatim from SKILL.md on 2026-11-01.

## Router engine (historical: superseded by Walter Router)

Walter Router now owns routing (tiers L1/L2/L3 by the owner's method in `/walter/cognition/router/docs/TIERS.md`, specialised
tasks by weighted leaderboards): do not route from `router_matrix.json`; use `walter-router route "<request>"` or
`walter-router pick <task>`. `router.py` stays for comparison only, after a fresh collection. It implemented the
owner's original routing philosophy:

1. **Three intelligence levels derived from the AA Intelligence Pareto optimum**
   (from `upgrade_ladder` in the fresh snapshot):
   - L1 standard = the current `value_anchor`; never pin a historical named winner.
   - L2 high     = the current ladder knee: the last tier before the sharpest fall in
     `marginal_score_per_dollar_from_previous` (`ladder_knee()` in `router.py`).
   - L3 max      = the current `quality_ceiling`.
2. **Default routing** stays on the required level's model (cheapest sufficient).
3. **Conditional escalation, only when the specific action needs a domain
   skill**: then take the BEST model of that domain per Design Arena human
   preference (e.g. frontend → Kimi K3, gamedev → Claude Opus 5, SVG → GPT-5.6
   Sol), with the cost delta vs the default shown. A compromise line also shows
   the best design model whose AA task cost does not exceed the default level's current
   task cost (read from the fresh ladder, never a pinned constant).

```bash
python3 ~/.hermes/skills/research/aa-pareto-model-optimizer/scripts/router.py            # full report
python3 ~/.hermes/skills/research/aa-pareto-model-optimizer/scripts/router.py "landing page"
python3 ~/.hermes/skills/research/aa-pareto-model-optimizer/scripts/router.py --level 2 "webapp react"
python3 ~/.hermes/skills/research/aa-pareto-model-optimizer/scripts/router.py --list-domains
```

- Domains: `frontend`, `3d`, `gamedev`, `dataviz`, `svg`, `brand`, `build`,
  `slides` — each with keyword triggers (length-weighted) mapped to specific
  Design Arena categories (NOT the Overall scale: a domain leader is the top
  Elo of its primary category; e.g. dataviz → Claude Opus 5 at 1389 in Data
  Viz, not Kimi K3's generic Overall score).
- Brand/logo may point to image generators (gpt-image-2) outside the text-LLM
  pool; they are flagged `in_llm_pool=false`.
- Outputs `router_matrix.json` + `router_matrix.csv` (levels + domain leaders).
- Needs `latest.json`, `designarena.json`, `model_profiles.json` in the cache
  (the former wrapper, manual run only, chains all four stages).

