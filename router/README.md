# Walter Router

Model catalogue + per-task model choice for W.Alter. Schema `models` in hindsight-pg (127.0.0.1:5433, creds in ~/.pgpass).
Plan and decisions: `/root/projects/walter-model-router/docs/PLAN-v2.md`.

## Flow (timer `walter-router-refresh` 03:30 UTC, after the 03:00 aa-pareto collection)
1. **Collect** → `models.snapshots` (deduplicated by sha256, 30-day retention, latest per kind always kept):
   AA intelligence, AA multimodal, Design Arena (files from the aa-pareto skill cache), Arena.ai (15 boards read
   from the pages' embedded data: text, French, coding, webdev, vision, document, search, agent, text-to-image,
   image edit, text-to-video, image-to-video, video edit), OpenRouter (`?output_modalities=all` + media prices
   from each model page's `displayPricing`, base unit = price ÷ `displayMultiplier`), Kie pricing, Codex account
   catalogue (read through Hermes), and the live `/models` (with prices) of OpenAI-compatible providers configured
   in Hermes (`config/providers.json`, today Arnict AI; key read at run time from `~/.hermes/.env`, sent as a
   header only). A failing source keeps its last good snapshot.
2. **Parse** → `models.benchmarks` (measured quality) and `models.offers` (callable, priced), linked through
   `models.canonical`/`models.aliases` (deterministic normalisation + justified manual aliases in `aliases.json`).
   Every media offer is classified (`walter_router/media.py`): `offer_kind` generation | fee | tool, `modes`
   t2i/i2i/t2v/i2v/r2v/v2v, `resolution`, `audio`, and `norm_price`/`norm_unit` (video per second, image per image,
   voice per 1000 characters). View **`models.catalog`** = one row per model and interface (name, modes,
   providers, price range, resolutions, release date, every leaderboard score, open weights / licence,
   content policy). `models.canonical.open_weights`/`license` come from Arena licences, AA `open_weights` and
   Hugging Face ids; `content_policy = 'unrestricted'` + `base_model_id` for uncensored / abliterated fine-tunes
   (they inherit the base model's score, flagged). View `models.open_models` lists both.
3. **Select** → `models.selection` per task: `best` (quality order among callable models), `value`/`L1-L3`
   (the skill's own Pareto code on the cheapest *real* price: AA list cost × provider/list price ratio),
   `frontier`. Subscription routes (Codex) are listed first, paid route kept as fallback.
4. **Alerts** → `models.alerts`: `challenger` (a model measured better than a pinned favourite on any board of
   the task, `models.task_benchmarks`), `unranked` (one per model: provider release < 30 days without any
   leaderboard score — recorded, **never sent**), `top3` (a model entering the top 3 of a board in a watched
   domain; first run = baseline), `source_stale`. A challenger is only kept when it is in the board's top 3
   (top 3 among models no dearer than the favourite for ratio / budget favourites). Telegram = one line per model
   (`catalog.line`: "🎬 name — modes — price per resolution — providers"; 🖼️ image, 🎬 video, 🗣️ voice,
   🎵 music, 💬 text, 🔓 unrestricted). Telegram via
   `hermes send` only for challengers, stale sources, and unranked models in an interface Monsieur has a
   preference on. Pinning records already-better models as `baseline` (no message).

## Commands
```
bin/walter-router migrate
bin/walter-router refresh [--no-notify] [--dry-run]
bin/walter-router pick <task> [--level L1|L2|L3]      # preferences first, then computed choice
bin/walter-router pick <task> --require unrestricted|open_weights   # hard constraint, best callable model
bin/walter-router prefer <task> [--objective value|best_available] [--pin model_id[/variant]] [--provider p] [--note ...]
bin/walter-router alerts [--all]
bin/walter-router verdict <alert_id> adopted|dismissed [--note ...]   # adopted challenger becomes the favourite
bin/walter-router status
```
Tests: `venv/bin/python -m pytest -q tests` (DB tests run inside a rolled-back transaction).
