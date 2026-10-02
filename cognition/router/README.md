# Walter Router

Model catalogue + per-task model choice for W.Alter. Schema `models` in hindsight-pg (127.0.0.1:5433, creds in ~/.pgpass).
Plan and decisions: `/root/projects/walter-model-router/docs/PLAN-v2.md`.

## Flow (timer `walter-router-refresh` 03:30 UTC, after the 03:00 aa-pareto collection)
1. **Collect** → `models.snapshots` (deduplicated by sha256, 30-day retention, latest per kind always kept):
   AA intelligence, AA multimodal, Design Arena (files from the aa-pareto skill cache), OpenRouter
   (`?output_modalities=all`), Kie pricing, Codex account catalogue (read through Hermes). A failing source
   keeps its last good snapshot.
2. **Parse** → `models.benchmarks` (measured quality) and `models.offers` (callable, priced), linked through
   `models.canonical`/`models.aliases` (deterministic normalisation + justified manual aliases in `aliases.json`).
3. **Select** → `models.selection` per task: `best` (quality order among callable models), `value`/`L1-L3`
   (the skill's own Pareto code on the cheapest *real* price: AA list cost × provider/list price ratio),
   `frontier`. Subscription routes (Codex) are listed first, paid route kept as fallback.
4. **Alerts** → `models.alerts`: `challenger` (a model measured better than a pinned favourite),
   `unranked` (provider release < 30 days without any leaderboard score), `source_stale`. Telegram via
   `hermes send` only for challengers, stale sources, and unranked models in an interface Monsieur has a
   preference on. Pinning records already-better models as `baseline` (no message).

## Commands
```
bin/walter-router migrate
bin/walter-router refresh [--no-notify] [--dry-run]
bin/walter-router pick <task> [--level L1|L2|L3]      # preferences first, then computed choice
bin/walter-router prefer <task> [--objective value|best_available] [--pin model_id[/variant]] [--provider p] [--note ...]
bin/walter-router alerts [--all]
bin/walter-router verdict <alert_id> adopted|dismissed [--note ...]   # adopted challenger becomes the favourite
bin/walter-router status
```
Tests: `venv/bin/python -m pytest -q tests` (DB tests run inside a rolled-back transaction).
