# Inventaire du code

> Généré par `walter-router docs --write`. Modifier les sources, puis régénérer ; ne pas éditer ce fichier.


## analysis/__init__.py

Analysis: understands the collected data and organises it in the database (parsing, identities, media


## analysis/alerts.py

Alerts: a pinned favourite overtaken, unranked new releases, stale sources — and their Telegram notification.

- `record(conn, kind: str, task: str, subject: str, evidence: dict, status: str, role: str='')` — Insert or refresh an alert; returns True when it is new. Verdicts and statuses are never overwritten.
- `_unit_cost(offers: list[dict], interface: str, modes: list[str] | None=None)` — 
- `_board_rows(conn, snaps: dict, benchmark: str, bench_task: str)` — 
- `_order(rows: list[dict])` — Distinct models of a board, best first (variants of one model count once).
- `new_best(conn, run_id: int, chg: dict | None=None)` — A new #1 for a specialised task is only PROPOSED (2026-10-16: « je dois toujours appuyer sur le
- `top3(conn, status_for_new: str | None=None)` — A model entering the top 3 of a leaderboard in a domain the owner watches (interfaces they have preferences on).
- `_raw_measure(theirs: dict, mine: dict)` — {'raw': [challenger, pinned, unit]} for a latency / WER board, read as measured.
- `challengers(conn, status_for_new: str='open', only_task: str | None=None, only_role: str | None=None, chg: dict | None=None)` — Models that overtake one of the owner's pinned favourites on any leaderboard of that task
- `unranked(conn)` — Models released recently on a provider with no measurement on any leaderboard yet (one alert per model).
- `stale_sources(conn)` — 
- `boards_down(conn)` — 2026-10-14: tell them when a leaderboard used by a task can no longer be read — the whole source
- `tiers(conn, run_id: int | None=None, chg: dict | None=None)` — When the owner's method (nightly L1/L2/L3 in models.selection) designates another model x reasoning level than
- `adopt_orchestrator(conn, model_id: str)` — The owner adopted a new orchestrator: point Hermes model.default/provider at its first route (subscription
- `postes(conn)` — Orchestrator fiche de poste vs the model Hermes really runs: a clearly better one (>= margin) is proposed.
- `nerfs(conn, run_id: int, chg: dict | None=None)` — An ACTIVE model (favourite, text tier, auto #1) lost score on a board of the task it is active for.
- `pareto(conn, run_id: int, chg: dict | None=None)` — A price drop (or a release) that puts a model on the text Pareto frontier.
- `billing(conn)` — Providers whose last probe found no credit left: one alert each, auto-cleared once topped up.
- `_watched_interfaces(conn)` — Interfaces the owner has a declared preference on: new unranked releases there are worth a message.
- `pending(conn)` — What goes to Telegram. Unranked releases are recorded but never sent (too many, unproven): a new model is
- `verdict(conn, alert_id: int, decision: str, note: str | None=None, role: str | None=None, _resolved: bool=False)` — Record the owner's answer. 'adopted' on a challenger also pins the challenger as the new favourite.

## analysis/aliases_admin.py

Validated name links (aliases) — how the 48 h analysis agent fixes naming gaps between sources

- `_read()` — 
- `_write(doc: dict)` — Learned links belong to the instance: written where they are read from (identity.AUTO_ALIASES), except the
- `add(conn, key: str, model_id: str, reason: str, origin: str='agent')` — 
- `remove(key: str)` — 
- `listing()` — 

## analysis/catalog.py

Model cards: what a model does, what it costs per resolution, where to call it and how it ranks — and the

- `card(conn, model_id: str, interface: str, modes: list[str] | None=None)` — Everything known about one model on one interface, from the latest snapshots.
- `money(x: float)` — 0.0525 -> '0,053' ; 1.2 -> '1,2' (French decimals, 2 significant digits under 1 $).
- `price_text(c: dict)` — 
- `icon(c: dict)` — 🖼️ image, 🎬 video, 🗣️ voice, 🎵 music, 💬 text; 🔓 added for an unrestricted model.
- `line(c: dict)` — 

## analysis/changes.py

What CHANGED since the previous cycle — the only thing worth a Telegram message (2026-10-04).

- `_versions(conn, snapshot_id: int)` — Board -> version label of a snapshot. The first AA v5.0 snapshot (2026-10-28) only had `index_version`.
- `rebased_boards(conn, cur: int, prev: int)` — {board: {'before', 'after'}} for the boards whose version label changed. A label missing from the latest
- `_previous(conn, kind: str)` — 
- `events(conn)` — {'new': {model_id: [why]}, 'nerf': {model_id: [why]}, 'price_drop': {model_id: [why]},
- `changed(ev: dict, model_id: str)` — Reasons a model counts as news (new or cheaper).
- `rebased_intelligence(ev: dict)` — The reason to put every text tier to the owner again: the AA Intelligence Index changed version.
- `frontier_entrants(conn, run_id: int)` — Text Pareto frontier points of this run that were not on the previous run's frontier.
- `latest_snapshot_ids(conn)` — 

## analysis/decision_pareto.py

Decision models on three axes (2026-10-16): intelligence (AA Decision Index, higher), speed (median

- `points(conn, modes: list[str] | None=None)` — 
- `dominates(a: dict, b: dict)` — 
- `frontier(pts: list[dict])` — 
- `verdict(new: dict, current: dict | None, pts: list[dict])` — Where a newcomer stands: on the frontier?, models it dominates, models dominating it, the frontier itself.

## analysis/dossier.py

One JSON dossier per task, rebuilt at every refresh (models.dossiers): everything the router / orchestrator

- `build(conn, task: str, run_id: int, n: int=8)` — 
- `_ranking(conn, t: dict, pinned: set[str], n: int)` — Every measured model of the task in composite order (callable or not), the owner's pinned models always shown
- `build_all(conn, run_id: int)` — 
- `latest(conn, task: str)` — 

## analysis/identity.py

Deterministic model identities: every external key is normalised to (model_id, variant).

- `canon(base: str)` — Spelling-only normalisation shared by every namespace: glued family/version and '.0' versions.
- `_load_manual()` — aliases.json (hand-written) + config/aliases_auto.json (validated additions by the analysis agent).
- `reload()` — 
- `slugify(text: str)` — 
- `_variant_from_paren(name: str)` — 'Claude Opus 5.5 (xhigh with fallback)' -> ('Claude Opus 5.5', 'xhigh'); 'based on ...' notes are dropped.
- `_compact(text: str | None)` — 
- `stt_name(model: str, host: str | None=None)` — AA Speech-to-Text row name without its host: 'Whisper (L, v3, Turbo), Groq' -> 'Whisper Large v3 Turbo',
- `policy(model_id: str)` — ('unrestricted', base model) for uncensored / abliterated fine-tunes, else ('standard', None).
- `normalize(namespace: str, key: str, name: str | None=None)` — Return (model_id, variant) for an external key of a namespace (aa | da | mm | arena | openrouter | kie | codex).

## analysis/ingest.py

Writes a snapshot and its parsed rows, with identities (models.canonical / aliases).

- `_display_name(namespace: str, name: str | None)` — 
- `_apply_meta(conn, namespace: str, model_id: str, meta: dict | None)` — Open weights / licence: 'open' from any source wins (Arena licence, AA open_weights, a Hugging Face id);
- `_ensure_identity(conn, namespace: str, key: str, model_id: str, vendor: str | None=None, name: str | None=None)` — 
- `_f(v)` — 
- `_insert_endpoints(conn, sid: int, doc: dict)` — Hosts behind OpenRouter (research.prices.openrouter_endpoints) -> models.endpoints, prices in $/M tokens.
- `_insert_rows(conn, sid: int, kind: str, doc: dict)` — (Re)derive benchmarks/offers of one snapshot from its raw document with the current identity rules.
- `store(conn, kind: str, doc: dict, fetched_at: datetime, url: str)` — Insert the snapshot (deduplicated by content) and (re)derive its rows. Returns (snapshot_id, is_new).

## analysis/knowledge.py

The owner's model knowledge and the intent-aware decision built on it.

- `load()` — 
- `set_level(task: str, level: str, pin: str, why: str, provider: str | None=None, description: str | None=None, evidence: str | None=None, fallback=KEEP)` — One writer for the owner's declared text tiers (knowledge.json "levels"), the source `declare` re-applies
- `norm(text: str)` — 
- `hits(text: str, signals: list[str])` — 
- `declare(conn, doc: dict | None=None)` — Apply knowledge.json: profiles, roles (favourites per objective), retired roles, affinities. Idempotent.
- `affinity(conn, model_id: str, task: str)` — 
- `tie_margin(unit: str | None)` — 
- `tie_break(conn, task: str, rows: list[dict], score='quality', unit='quality_unit')` — Close calls: every model within the tie margin of the current leader forms a group; inside the group
- `level_fallback(task: str, level: str | None)` — Declared fallback (model_id/variant) of a text tier, used when every route of the pinned model fails.
- `declared_fallbacks(model_id: str, task: str, level: str | None, require: str | None)` — Models the owner declared to run when every provider of `model_id` failed, in order, as (model_id, variant):
- `effective_policy(conn, model_id: str)` — 
- `profile(conn, model_id: str)` — 
- `_role_line(conn, task: dict, p: dict)` — 
- `decide(conn, task: str, intent: str, level: str | None=None, jev: dict | None=None)` — Free-text request -> role (objective) -> favourite model -> route, workflow and a brief for the orchestrator.

## analysis/media.py

What a media offer actually sells: generation mode(s), output resolution, audio, and a comparable unit price.

- `resolution(text: str, tier_label: str='')` — 
- `resolution_rank(res: str | None)` — Sort key: 480p < 720p < 1080p ~ 1K < 2K < 4K.
- `audio(text: str)` — 
- `classify(interface: str, label: str, input_modalities: list[str] | None=None)` — Classify one offer. `label` is the provider's own SKU text (without the model id); `input_modalities`
- `norm_price(interface: str, unit_price: float | None, unit: str | None, label: str)` — Price in the interface's comparable unit; 'per video' with an explicit duration ('10s', '6.0s') -> per second.
- `compatible(offer_modes: list[str] | None, wanted: list[str] | None)` — A generation offer fits a task when it declares one of the task's modes; a generic SKU (no declared mode)
- `short_modes(modes: list[str])` — 

## analysis/pareto.py

Pareto mathematics of the text tiers: the cost/score frontier with epsilon and pragmatic pruning

- `finite_number(value: Any)` — 
- `compact_frontier_row(row: dict[str, Any], score_field: str, cost_field: str)` — 
- `_log_cost_slope(left: dict[str, Any], right: dict[str, Any], score_field: str, cost_field: str)` — 
- `supported_frontier(frontier: list[dict[str, Any]], score_field: str, cost_field: str)` — Keep supported Pareto points on score versus logarithmic cost.
- `standout_frontier(frontier: list[dict[str, Any]], score_field: str, cost_field: str, minimum_knee_strength: float=2.0)` — Keep endpoints and local knees relative to strict-frontier neighbors.
- `select_value_anchor(supported: list[dict[str, Any]], score_field: str, cost_field: str)` — Select the strongest global knee on the supported Pareto frontier.
- `build_upgrade_ladder(strict: list[dict[str, Any]], value_anchor: dict[str, Any], score_field: str, cost_field: str, display_cost_field: str | None=None)` — Build the raw-cost concave envelope above a global value anchor.
- `compact_frontier_rows(rows: list[dict[str, Any]], score_field: str, cost_field: str)` — 
- `epsilon_prune(frontier: list[dict[str, Any]], score_field: str, cost_field: str, min_score_gain: float, max_cost_premium_pct: float)` — Remove a cheaper frontier row when a near-priced, better row exists.
- `pragmatic_prune(rows: list[dict[str, Any]], score_field: str, cost_field: str, min_gain: float, max_incremental_cost_per_score_point: float)` — Filter low-gain and high-marginal-cost steps against retained neighbors.
- `make_frontier(rows: list[dict[str, Any]], score_field: str, cost_field: str, minimum_score: float, min_gain: float, epsilon_score_gain: float, epsilon_cost_premium_pct: float, minimum_knee_strength: float, max_incremental_cost_per_score_point: float=0.75)` — 
- `ladder_knee(tiers: list[dict[str, Any]], min_drop: float=2.0)` — Return the upgrade-ladder tier just before the sharpest fall in marginal return.

## analysis/parse.py

Understanding a snapshot: leaderboard rows -> models.benchmarks, catalogue rows -> models.offers.

- `_num(value: Any)` — 
- `_mm_unit_price(row: dict)` — AA list price normalised to the provider units we compare against (reference only, never 'callable').
- `parse_benchmarks(kind: str, doc: dict)` — 
- `_or_name(name: str | None)` — 'Black Forest Labs: FLUX.3 Image' -> 'FLUX.3 Image'; short names keep their vendor ('MiniMax H3', 'HeyGen Video 1').
- `_kie_interface(rec: dict)` — 
- `_media_fields(interface: str, label: str, unit_price: float | None, unit: str | None, inputs: list[str] | None=None, tier_label: str='')` — What the offer sells (media.classify) and its price in the interface's comparable unit.
- `parse_offers(kind: str, doc: dict)` — 

## analysis/postes.py

Fiches de poste: which model fits a JOB (orchestrator, agent worker), not only a task.

- `_board(conn, snaps: dict, benchmark: str, task: str)` — 
- `_access(conn, snaps: dict)` — 
- `rank(conn, poste: str, limit: int=8)` — 
- `current_orchestrator()` — model.default / model.provider of the live Hermes config (read-only text parse); nothing once Hermes is

## analysis/recommend.py

A recommendation in the proposal message (2026-10-16: « à la place de 'meilleur sur les 3 axes', ajoute

- `_per_call(point: dict)` — Same basis for both models: AA cost per task (AA cost per 1M tasks / 1e6).
- `_volume(conn, task: str)` — Decisions per day attributable to this task over the last 14 days.
- `facts(conn, alert: dict, new: dict, cur: dict)` — 
- `fallback_text(new: dict, cur: dict)` — 
- `recommendation(conn, alert: dict, new: dict, cur: dict)` — Stored in the alert's evidence ('reco'); computed once.

## analysis/refresh.py

The router's cycle as the analysis runs it: research collects (or the latest snapshots are re-derived), then the

- `rederive(conn)` — Re-derive the latest snapshot of every source with the current identity rules (no network).
- `refresh(notify: bool=True, dry_run: bool=False, skip_collect: bool=False)` — 

## analysis/scoring.py

One quality score per task from several leaderboards (AA, Arena, Design Arena, BridgeBench...).

- `_reliability(row: dict)` — 
- `board_quality(rows: list[dict])` — Best row per model on one board, with its 0-100 quality and rank.
- `composite(conn, task: str, snaps: dict | None=None)` — Every model measured on at least one board of the task, best composite first.

## analysis/select.py

Compute ranked candidates per task from the latest snapshots, on the cheapest *real* price.

- `latest_snapshots(conn)` — 
- `board_snapshot(conn, snaps: dict[str, int], benchmark: str, bench_task: str)` — Snapshot to read one board from: the latest of its source, or — when the board is empty there (page changed,
- `load_offers(conn, snaps: dict[str, int])` — 
- `blended(offer: dict)` — AA's blended token price: 3 parts input, 1 part output.
- `chat_route(offers: list[dict], list_cost: float | None, modes: list[str] | None=None)` — Cheapest paid route for a chat model, scaling AA's list-price task cost by the provider/list price ratio.
- `_fields(o: dict)` — Stored classification of an offer (models.offers columns), or computed from its key when absent.
- `decision_route(offers: list[dict], modes: list[str] | None=None)` — Cheapest Decisions-API offer (decision models are billed on input tokens only) that reads every input the
- `media_route(offers: list[dict], interface: str, modes: list[str] | None=None)` — Cheapest generation offer in the interface's comparable unit (video per second, image per image), restricted
- `_intelligence_index(conn, snaps: dict[str, int], offers: dict[str, list[dict]])` — 
- `_row(task: str, level: str, rank: int, cand: dict, **extra)` — 
- `_ladder(cands: list[dict], minimum_score: float, cost_cap: float)` — 
- `_tier_rows(cands: list[dict])` — The owner's three text tiers (tiers.py) on the AA frontier of callable model x reasoning level, real costs.
- `_best_by_composite(conn, t: dict, snaps: dict, offers: dict, cands: list[dict], n: int=6)` — 'best' level: callable models ordered by the weighted multi-board score (scoring.composite).
- `family(model_id: str)` — 'gpt-image-2-5-sunburst' -> ('gpt-image', (2, 5), 'sunburst'); 'gpt-image-2' -> ('gpt-image', (2,), '').
- `same_line(model_id: str, newer_id: str)` — newer_id is a later version of the SAME product line: same prefix, higher version, and it keeps every product
- `_executable_first(conn, t: dict, ranked: list[dict], offers: dict)` — The owner (2026-10-14, logo): the best measured model must be one Walter can run; and when a newer version of
- `general_points(conn)` — Every callable model x reasoning level on the AA Intelligence Index with its real cost per AA task (the cloud
- `compute(conn)` — 
- `save(conn, run_id: int, rows: list[dict])` — 

## analysis/telegram.py

Telegram side of the alerts: one message per piece of news with its buttons (2026-10-16 owner's format: header

- `_challenger_line(conn, a: dict)` — 
- `_short_board(name: str)` — 
- `_fr(x, digits: int)` — 
- `_head(c: dict)` — 
- `_money_line(c: dict)` — 
- `_why(e: dict)` — 
- `_plan_block(a: dict)` — 2026-10-22: a billing e-mail differs from the declared plans.
- `_block(conn, a: dict)` — 
- `_decision_block(conn, a: dict, task: dict)` — Decision model proposal, short (2026-10-16: « trop gros, des informations inutiles »): who replaces
- `_group_key(conn, a: dict)` — 
- `_board_fr(key: str)` — 'Arena text_to_video' -> 'Arena vidéo depuis texte'.
- `_modes_fr(modes: list[str])` — 
- `_origin(e: dict)` — 'nouveau chez kie' -> 'Nouveau chez Kie'.
- `_price_lines(c: dict, current: dict | None=None)` — One line per resolution with its cheapest provider, then the current model's entry price.
- `_challenger_group(conn, group: list[dict])` — One block for one new model that beats one or several of the owner's choices (2026-10-14:
- `_route_line(conn, a: dict, c: dict)` — '🔁 Fournisseurs : Kie → OpenRouter · Secours : Wan 3' for a media model (what would run if adopted).
- `render(alerts: list[dict], conn=None, typed: bool=False)` — 
- `render_each(alerts: list[dict], conn=None, typed: bool=False)` — One message per piece of news (2026-10-16: « 2 messages différents, pas un gros message »).
- `keyboard(conn, alerts: list[dict])` — 
- `_name(conn, model_id: str | None)` — 
- `_button_text(conn, a: dict, label: str, code: str)` — '✅ Passer à Grok Imagine Video 1.5' / '✖️ Garder MiniMax H3' (names, not numbers: several news per message).
- `send_with_buttons(text: str, rows: list[list[dict]])` — Through Walter's own Telegram door (lot E6, 2026-11-10: `walter-telegram send`, no longer Hermes' bot): it
- `_assign_refs(conn, alerts: list[dict])` — Short numbers the owner can answer with (1, 2, 3…), unique among alerts still awaiting their answer.
- `notify(conn, dry_run: bool=False)` — 

## analysis/tiers.py

The owner's method for the three functional text tiers (declared 2026-10-02).

- `frontier(points: list[dict])` — points: {'model_id', 'variant', 'score', 'cost', ...}; strict Pareto frontier with 'marginal' filled.
- `_gain(a: dict, b: dict)` — Points per extra dollar going from a to b.
- `compute(points: list[dict], floor: float=QUALITY_FLOOR, band: float=CEILING_BAND, knee_drop: float=KNEE_DROP)` — 

## cli.py

walter-router CLI: migrate | refresh | pick | prefer | alerts | verdict | status | route | run | web …

- `feedback(conn, model: str, rating: int, task: str | None, note: str | None)` — 
- `_instance_env()` — HERMES_HOME, LOG, CONTROL_ENV, LIBRARY_URL and ANALYSIS_PROMPT (the shipped analysis prompt
- `build_parser()` — 
- `main(argv: list[str] | None=None)` — 

## documentation.py

Reproducible reference documentation. Metadata only; never read provider/account payloads.

- `database(conn)` — 
- `source_files()` — 
- `normal(value)` — 
- `inventory()` — 
- `cli_reference()` — 
- `_neutral_metadata(value, owner)` — Remove the active owner's address form from public descriptive catalog metadata.
- `collect(offline=False)` — 
- `cell(value)` — 
- `render(c)` — 
- `maintain(write=False, offline=False)` — 

## guardian/__init__.py

Guardian of the Walter Router: keeps the module working without the owner (2026-10-26).


## guardian/__main__.py

walter-router-guardian check | run [--no-agent] [--no-tests] [--no-notify] [--dry-run] | status

- `main(argv: list[str] | None=None)` — 

## guardian/checks.py

Deterministic detection: what is wrong with the module right now. No model is called here.

- `sources(conn)` — 
- `cycle(conn)` — 
- `provider_side(detail: str)` — 'ours' (the request looks wrong: repairable here), 'account' (key, credit: the owner's), 'external'.
- `providers(conn)` — 
- `dirty_paths(root=None)` — Files with uncommitted changes in the live module (someone's work in progress), relative to its root.
- `run_tests(root, timeout: int=TEST_TIMEOUT)` — The module's test suite in `root`: {ok, failures: {node id: one-line reason}, tail}.
- `tests(root=None)` — Failing tests, except those whose test file is itself someone's uncommitted work (still being written).
- `docs_check()` — `walter-router docs --check`: the generated reference against code and schema. {} when the installed version
- `docs()` — 
- `detect(conn, with_tests: bool=True)` — 

## guardian/repair.py

Repair of one incident by the L2 agent, on a copy of the module; deterministic gates decide whether it lands.

- `_git(cwd: Path, *args: str, check: bool=True)` — 
- `workspace(incident_id: int)` — A fresh copy of the live module with a git baseline: what the agent works on.
- `_render(incident: dict, module: Path)` — 
- `_readonly_script()` — The live module, the instance configuration and the system units are read-only for the agent.
- `verdict_of(output: str)` — The agent's closing JSON (outcome, cause, changes, summary): the last object carrying an `outcome`.
- `agent(incident: dict, module: Path)` — 
- `changed_files(module: Path)` — (status, path) of the agent's changes against the baseline; status D = deleted.
- `_asserts(text: str)` — 
- `verify_source(module: Path, kind: str)` — Read the source with the repaired code (no database write): rows parsed, or the error.
- `gates(module: Path, incident: dict, baseline: dict)` — Deterministic checks on the agent's patch. ok=False lists why it must not land.
- `_digest(path: Path)` — 
- `apply(module: Path, files: list[str], deleted: list[str], message: str)` — Copy the verified files into the live module, only where the live file is exactly what the agent started
- `regenerate_docs(message: str)` — Generated reference out of date: regenerate it (no model), and commit the regenerated files alone, unless one
- `_new(module: Path)` — 
- `prune(days: int=7, keep: set[str]=frozenset())` — Old workspaces go; those holding a deferred patch stay.

## guardian/run.py

One guardian pass: detect, follow incidents, act, tell the owner only what is worth it.

- `_now()` — 
- `_age_h(ts)` — 
- `sync(conn, problems: list[dict], tests_checked: bool)` — Open or refresh one incident per problem; close those no longer seen (a test incident only when the
- `_set(conn, inc: dict, status: str, verdict: dict | None=None, attempt: bool=False)` — 
- `reread_source(kind: str)` — The router's own read of one source (writes its snapshot when it works).
- `_needs_agent(inc: dict)` — 
- `commit_message(inc: dict, v: dict)` — Subject: which incident; body: the agent's cause and evidence, then who did the work.
- `_repair(conn, inc: dict, dry_run: bool)` — 
- `_retry_deferred(conn, inc: dict)` — A verified patch waiting for files someone else was editing: land it once they are free.
- `_docs(conn, inc: dict, dry_run: bool)` — Generated reference: regenerated mechanically, never by the agent; quiet when it works.
- `handle(conn, inc: dict, budget: list[int], dry_run: bool=False)` — 
- `_message(inc: dict)` — What the owner reads, once per outcome; None = nothing worth a message.
- `notify(conn, incidents: list[dict], send: bool=True)` — 
- `run(agent: bool=True, tests: bool=True, send: bool=True, dry_run: bool=False)` — 
- `status()` — 

## health.py

Health of the Walter Router module: last refresh, source ages, providers, subscriptions, dossiers (`walter-router

- `status()` — 
- `health()` — Is the router fed and usable? ok=False lists what is wrong (used by walter_health and the failure alert).
- `notify_failure()` — Called by systemd OnFailure: tell the owner on Telegram that the nightly refresh failed (one short message).

## hermes-plugins/kie-compat/__init__.py

Kie.ai compatibility shim (LLM request middleware; Hermes core untouched).

- `_strip_output_config(request: Any=None, base_url: Any=None, api_mode: Any=None, **_: Any)` — 
- `register(ctx: Any)` — 

## hermes-plugins/walter-router/__init__.py

Walter Router tools for Hermes (plugin; Hermes core is never patched). Thin: every decision and every run is the

- `_cli(*args: str, timeout: int=60, stdin: str | None=None)` — 
- `_tasks()` — 
- `_brief()` — What the agent must know to use the router (tools, levels, specialities, generation, constraints — no model
- `_spec(args: Mapping[str, Any])` — 
- `_handle_route(args: Mapping[str, Any], **_: Any)` — 
- `_handle_run(args: Mapping[str, Any], **_: Any)` — 
- `_handle_decide(args: Mapping[str, Any], **_: Any)` — 
- `_handle_verdict(args: Mapping[str, Any], **_: Any)` — 
- `_handle_feedback(args: Mapping[str, Any], **_: Any)` — 
- `_handle_plans(args: Mapping[str, Any], **_: Any)` — The owner's subscriptions (Walter Router plan/): list, change or cancel when he says so (2026-10-22).
- `_available()` — 
- `_home_chat()` — The owner's Telegram chat (gateway home channel); only they may press the buttons.
- `_wire_buttons(application: Any, adapter: Any)` — Buttons of the Walter Router notification (callback data 'wr:<a|d>:<ref>[:<role>]', sent by the
- `_web_commands()` — Telegram command → service, from the router gateway's own rule table (read once, at load).
- `_post_web(body: dict, timeout: float)` — 
- `_chunks(text: str, size: int=4000)` — 
- `_split_model(text: str)` — `[GPT-6 high] question` → ("GPT-6 high", "question"); without brackets the service keeps its own model.
- `web_exchange(service: str, text: str, chat_id: Any, message_id: Any, sent_at: float | None, reply: Any, *, model: str | None=None, files: list[tuple[str, bytes]] | None=None, send_file: Any=None)` — One owner message to a web service and its verbatim reply (`reply(str)` sends one Telegram message,
- `_wire_web_commands(application: Any, adapter: Any)` — Owner-only Telegram commands of the web services. Group -1 + ApplicationHandlerStop: the message never
- `_handle_web(args: Mapping[str, Any], **_: Any)` — POST /v1/web/converse through the router's own CLI (`walter-router web`); its JSON even on failure.
- `register(ctx: Any)` — 

## instance.py

What the Router needs from the active Walter instance, asked through its public interface (`walter instance`).

- `_walter(*args: str)` — 
- `_show()` — 
- `owner()` — How messages, notes and prompts name the person this instance serves (its declared address form).
- `config_path(name: str)` — An instance's own Router file (config/router/<name>) when it has one, else the shipped default.
- `host()` — Host bindings of the instance (config host.json): runtime profiles, cron jobs, publishing helpers.
- `hermes_active()` — Whether the instance still runs Hermes as a runtime the Router configures (host.json `hermes`; default active).
- `_expand(value: str)` — 
- `host_path(key: str)` — A path binding of host.json (absolute, ~/ or @instance/); None when the instance has none.
- `own_file(name: str)` — Where the instance keeps its own copy of a Router file it writes (config/router/<name>).
- `hermes_home()` — The Hermes home this instance runs (HERMES_HOME, else the instance's declared harness home).
- `hermes_bin()` — 
- `hermes_python()` — 
- `child_env(**extra: str)` — Environment of a Hermes child process run on behalf of the Router.
- `secret_value(name: str)` — A key the Router component is granted under NAME (Walter Secrets: instance accounts/<id>.toml, `allow` + [env],
- `state_file(name: str)` — A file the Router generates for the instance (state/router/<name>), e.g. the agents' brief.

## interface/__init__.py

Interface: the model library page (English, French), rebuilt and published after every change.


## interface/library.py

The model library as the owner reads it (2026-10-14): per task and category, the model in use, who chose it, the

- `provider_label(route: dict)` — Gateway-only routes have no direct Hermes provider; show their actual provider name.
- `subscription_label(routes: list[dict])` — Name the actual subscription instead of labelling every subscription as Codex.
- `_name(conn, mid: str | None)` — 
- `best_hosts(conn)` — model_id -> usage (interactive | background) -> cheapest usable host behind OpenRouter (models.best_endpoints).
- `_chat_price(offers: dict, mid: str, prov: str, hosts: dict | None=None)` — 
- `_route_price(route: dict, offers: dict, mid: str, hosts: dict)` — Price of one chat route as Walter pays it: a subscription at its cost price per token (plan price / API value it
- `_media_price(offers: dict, mid: str, prov: str, interface: str)` — 
- `sel_model_id(route: dict)` — Canonical model id of an execution route ('openai/gpt-6.1-sol', 'gpt-6-1-sol' -> 'gpt-6-1-sol').
- `_service_price(offers: dict, mid: str, prov: str, iface: str)` — 
- `boards_of(conn, task: str)` — « Arena vidéo depuis texte 50 % · AA vidéo depuis texte 50 % » (fr, en): the weighted leaderboards behind the
- `rows(conn)` — 
- `render(rs: list[dict])` — 
- `_context(conn)` — 
- `render_html(rs: list[dict], ctx: dict)` — 
- `publish(conn, deploy: bool=True)` — Rebuild the library page in the instance's build folder (host.json site_build) and deploy it to Cloudflare

## interface/page.py

Library web page (v3, 2026-10-14: « le design fait trop IA, pas pro »).

- `_route(text: str | None)` — 
- `_chart(points: list[dict], frontier: list[dict], levels: dict[str, dict], key: str='cost')` — 
- `_da(conn, rs: list[dict])` — 
- `_table(rs: list[dict])` — 
- `_tok(n: float | None)` — 
- `_usd(x: float | None)` — 
- `_subscriptions(conn)` — Subscriptions pane (information only): our measurement on the owner's account + SemiAnalysis' plan values.
- `_plan_costs(conn)` — Cost price of a token per plan (2026-10-22): what the router uses to price a subscription route.
- `_plan_facts(conn)` — Everything known about each plan, with its source (web research, billing mails, measures, the owner).
- `_plan_forms(subs: list[dict])` — Edit a plan, cancel it, or add one (2026-10-22). Sent to /api/plans (Access + HMAC), applied by
- `render(conn, rs: list[dict], ctx: dict)` — 

## interface/translate.py

English version of the library page (2026-10-14: « une version anglaise et française à choisir en bas »).

- `_text(t: str)` — 
- `_tag(tag: str)` — 
- `to_english(html: str)` — 

## llm/antigravity_subscription.py

Antigravity subscription transport (Google AI Pro / Ultra): the official Antigravity CLI, text only.

- `base_id(cli_id: str)` — Router offer key of a CLI model id: the reasoning level is a route parameter, not a model
- `cli_model(model: str, effort: str | None, verified: list[str])` — The verified CLI id for a router model + reasoning level (the closest level the account offers).
- `_text(content)` — 
- `prompt_of(messages: list[dict], response_format: dict | None=None)` — One prompt from OpenAI chat messages: instructions, then the conversation, then the message to answer.
- `_paths(config: dict)` — 
- `_forget(state: Path, conversation: str | None)` — Delete what the CLI kept of this call; summaries of past calls only when no other call is running.
- `_command(config: dict, model: str, schema: dict | None, timeout: float)` — 
- `_usage(u: dict | None)` — 
- `_failure(result: dict, stderr: str)` — 
- `completion(config: dict, *, model: str, messages: list, stream: bool=False, timeout=None, reasoning_effort: str | None=None, response_format: dict | None=None, tools=None, **_)` — OpenAI-shaped answer (ModelResponse, or an async iterator of chunks when streaming) from one CLI call.

## llm/claude_subscription.py

Claude subscription transport; Walter owns every message, tool and model parameter.

- `record_usage(config: dict, response)` — Metadata-only actual subscription usage; never prompts, outputs or CLI synthetic token counts.
- `owned_payload(payload: dict, native: dict, model: str)` — Allow only native billing attribution; never import CLI messages, tools or settings.
- `acknowledgement(model: str)` — Terminate the CLI after one transport request, without giving it real model output.
- `completion(config: dict, access_token: str, **kwargs)` — OpenAI completion, including real streaming/tool calls, over native subscription transport.

## llm/gateway.py

exec" "$(dirname "$(readlink -f "$0")")/venv/bin/python3" "$0" "$@"  # sh: run on the module venv

- `_walter(*args: str)` — Walter's public interface (`walter` on the PATH): module roots and the active instance.
- `_instance_path(value: str)` — 
- `provider_key(env_name: str)` — The provider key the walter-llm component is granted under `env_name` (walter_secrets.grants: the instance's
- `_read_key(env_name: str)` — 
- `_ledger()` — 
- `_ledger_add(entry: dict)` — 
- `test_budget()` — Paid spend of test runs over the window against the cap (+ the owner's approvals in the same window), USD.
- `_price_usd(route: dict, usage: dict | None, body: dict)` — Cost of one call from its usage (or, before the call, from the request size) at the route's price.
- `_priced(route: dict, telemetry: dict, body: dict)` — A paid call the provider reports no cost for (Venice, Kie…) gets its cost at the router's price for this
- `test_gate(route: dict, body: dict)` — None when this paid call of a test fits the budget, else the refusal (and one Telegram notice per window).
- `_charge(route: dict, entry: dict, telemetry: dict, body: dict)` — Record the paid spend of a test call (provider cost, else estimated from its usage or size).
- `_telegram(text: str)` — One message to the owner through Walter's Telegram door (`walter-telegram send`, lot E6; best effort).
- `approve_tests(eur: float, note: str='')` — The owner's approval of EUR more paid spend for tests, valid for the window.
- `_router(*args: str)` — 
- `exact_task(requested: dict)` — `exact:<model_id>[@<provider>]` for a run whose plan names a model, else None (malformed = None too).
- `_refresh(task: str)` — task = a router task, task/LEVEL for one of the instance's text tiers ("general/L2"), or exact:<model>[@<provider>]
- `decision(task: str)` — The router's routes for a task. A stale entry is served at once and refreshed in the background (a phone call
- `_refresh_chain()` — 
- `decision_chain()` — The Router's decision models in order (`walter-router decision-chain`: the owner's pinned / the cycle's best
- `structured_key(env_name: str)` — provider_key for the decision / rerank adapters, with a refusal that names what to provision (the variable and
- `warm()` — Fill the route cache at start-up for every chat task (background).
- `chat_tasks()` — 
- `owner_tasks()` — Chat tasks an owner message can ask for: the internal postes (memory extraction, compression, voice…) are
- `litellm_target(route: dict)` — LiteLLM arguments for one router route, or None when this gateway cannot run it (yet).
- `provider_completion(route: dict, **kwargs)` — One provider transport; Claude's native client contributes no agent context or tools.
- `claude_accounts(config: dict)` — subscription id -> Walter Secrets grant, first = the default account (before accounts: one grant).
- `_rate_limited(exc: BaseException)` — 
- `start_completion(route: dict, kwargs: dict, stream: bool, waits: tuple | None=None)` — (response, iterator, first chunk): the call, up to its first token when streaming. A subscription's rate-limit
- `codex_access_token()` — W.Alter's Codex access token, from its grant (renewed through the Codex CLI by walter-secrets).
- `_codex_account_id()` — 
- `_install_codex_auth()` — LiteLLM's chatgpt provider reads W.Alter's Codex CLI session (read-only) instead of its own device login.
- `_install_codex_stream_arguments()` — Parallel tool calls on the ChatGPT backend stream no argument deltas: the arguments come only in each call's
- `codex_cache_session(agent: str, task: str, body: dict, correlation: dict)` — The ChatGPT backend keeps a prompt prefix warm on the server a session id is routed to; LiteLLM draws a new id
- `chatgpt_ready()` — 
- `json_instruction(fmt: dict)` — 
- `as_json(text: str | None)` — The JSON object of a Codex answer; ValueError (= next route, which honours response_format) when there is none.
- `exact_call(spec: dict)` — Local router transport: one provider, one model, no retries or model fallbacks.
- `_usage(resp)` — 
- `_number(value)` — A finite nonnegative measurement, or unknown when missing or malformed.
- `_telemetry(resp)` — Vendor-reported cost and transport estimate stay distinguishable; absence is never zero.
- `_uuid(value)` — Validate a local correlation identifier without echoing its supplied value.
- `_dsh_session(value)` — Accept DSH's native session-UUID and bare UUID forms, preserving exact local identity.
- `_session_run(session: str)` — The public metadata-only lookup; no database import or global most-recent-run guess.
- `_run_metadata(run_id: str)` — Validate explicit request correlation through Memory's metadata-only public CLI.
- `_channel(row: dict)` — The channel of an identified run, for the test budget and the journal: `test` when the run was asked by a test
- `_correlation(request, body: dict, agent: str)` — Request-local transport metadata. DSH's public pi-ai cache key carries its native session identity only
- `planned_task(asked: str, requested: dict | None)` — (Router task for this call, what the plan set). Lot 2 (2026-11-07): `auto` takes the task and tier the
- `_text_parts(content)` — 
- `rule_answer(requested: dict | None, body: dict)` — The preflight's rule answer, only when this request ends on the very owner message it answers (its hash):
- `_rule_completion(text: str)` — 
- `_rule_stream(text: str)` — 
- `_rule_routing(run_id: str)` — 
- `_record_attempt(row: dict, entry: dict)` — Persist through public ports. DSH routing becomes applied only after an observed response.
- `log(entry: dict)` — 
- `web_services()` — 
- `_browse_converse()` — Browse's public client (walter_browse.converse), in process: no subprocess on the fast path.
- `web_converse(agent: str, body: dict)` — 
- `cost_headers(telemetry: dict)` — The call's cost for the caller's own ledger (Walter Memory's system.model_calls): reported by the provider, or
- `route_state(route: dict)` — 
- `selection_plan(d: dict)` — 
- `selection_check(plan: list[dict])` — True when every subscription route with quota left comes before every paid route (the owner's rule).
- `log_selection(agent: str, task: str, d: dict, chosen: int | None, passed: list[dict], correlation: dict)` — 
- `build_app()` — 
- `add_agent(name: str, cred_file: str, ref: str='WALTER_LLM_TOKEN')` — New token for NAME (one per agent: rotates). cred_file = a DSH credentials YAML, or `env:FILE[:VAR]` = a

## llm/structured.py

Structured model calls of walter-llm (SOCLE A6, 2026-11-11): typed decisions and rerank.

- `merge_answers(samples: list[dict])` — The mean of several answers to the same questions. noul: mean probability. choice: mean probability per option,
- `provider_of(model: str)` — 
- `is_free(model: str)` — 
- `reason(exc: BaseException)` — A short, safe reason for one failed attempt.
- `_error_code(data)` — 
- `_json(resp)` — 
- `_float(value)` — 
- `decide_once(client, key, model: str, state: dict, questions: dict, timeout: float)` — One decision call on its provider → {answers, usage, model, cost_usd, cost_status, input_tokens}.
- `_requested(body: dict, offered: list[str])` — The models to try: the Router's list, or the caller's narrowing of it (each must be offered).
- `_floor(body: dict)` — 
- `_timeout(body: dict)` — 
- `_straggler(body: dict)` — Seconds the late samples are given once a majority has answered; `straggler_s: null` waits for all of them.
- `_samples(once, n: int, grace: float | None)` — n parallel samples. Once a majority has answered, the others get `grace` seconds, then are dropped: the mean
- `_route_level(why: str)` — 
- `decisions(body: dict, *, chain: list[str], key, client, log, balance=None)` — Execute a decision request along the Router's chain. `log(entry)` receives one entry per physical call.
- `rerank_once(client, key, model: str, query: str, documents: list[str], top_n: int, timeout: float)` — 
- `rerank(body: dict, *, routes: list[dict], key, client, log, balance=None)` — Execute a rerank request on the Router's `rerank` poste routes, in order.

## paths.py

Folders of the Walter Router module (software side; instance data comes from walter_router.instance).


## plan/__init__.py

Plan: the owner's subscriptions, a part of Walter Router on its own (owner, 2026-10-22).


## plan/codex_account.py

The owner's ChatGPT/Codex account read with W.Alter's OWN Codex session (2026-11-10: no longer through Hermes).

- `_token()` — 
- `headers(token: str)` — Bearer + the workspace headers the backend derives from the OAuth JWT (account id, data residency).
- `_get(path: str, timeout: int=30)` — 
- `ranked(entries: list)` — Visible slugs by (priority, slug): `visibility: hide` entries are not offered to the account.
- `catalog()` — Model slugs the account may run (first client version that answers a non-empty list).
- `windows(payload: dict)` — Quota windows of a /wham/usage answer, named by their published duration (position only as fallback).
- `usage()` — 

## plan/declared.py

The owner's plans (subscriptions), editable from anywhere (owner, 2026-10-22: « les plans peuvent être ajoutés dans

- `_path()` — 
- `read()` — 
- `_write(doc: dict, why: str)` — 
- `upsert(sub_id: str, fields: dict, why: str, source: str='owner')` — Create or change one plan. Unknown fields are refused; a new plan needs vendor, plan and price.
- `retire(sub_id: str, why: str, source: str='owner')` — A cancelled plan leaves the active list but stays in `retired` with its date.
- `bind_claude_meter(sub_id: str, why: str)` — One-writer activation of the real Claude quota and bridge usage, preserving plan/price/history.
- `expiring(conn, days: int=30)` — A dated offer (`until`, e.g. Google AI Pro 15 months) ending within `days` becomes one Telegram notice.

## plan/mail.py

Plan changes read from billing e-mails (owner, 2026-10-22: « par events en analysant les mails »). Walter Memory

- `_token()` — 
- `_get(token: str, path: str)` — 
- `parse(sender: str, subject: str, snippet: str)` — vendor, plan, amount, currency, event of one subscription mail (None when it is not one).
- `_match(found: dict, plans: list[dict])` — 
- `proposal(found: dict, plans: list[dict])` — What the owner is asked to adopt given the LATEST mail of a plan, or None when it matches what is declared.
- `scan(conn, days: int=120)` — Read the vendors' subscription mails of the last `days`; store each once; propose on the LATEST event per plan.

## plan/news.py

A new benefit or change on a plan the owner has -> one Telegram notice each (owner, 2026-10-22: « s'il y a un nouvel

- `clean(text: str)` — 
- `body_text(token: str, mid: str, limit: int=420)` — First real sentences of the mail (text part, else the HTML without tags), boilerplate lines dropped.
- `_vendors_owned()` — 
- `_sender_vendor(sender: str, owned: dict[str, str])` — 
- `from_mail(conn, days: int=NEWS_DAYS)` — New product / plan mails from the vendors of the owner's plans -> evidence + notice. Returns alert ids.
- `from_web(conn, evidence_ids: list[int])` — Facts the web research just added for one of the owner's plans, unless the same fact was already known.

## plan/quota_watch.py

Subscription meters on the Walter bus (information only): after agent turns, re-read the meter of the plan that turn used.

- `react(events: list[dict])` — 
- `sweep()` — 
- `main()` — 

## plan/subscriptions.py

The owner's subscriptions — information only, no routing effect (2026-10-14).

- `doc()` — 
- `load()` — 
- `get(sub_id: str)` — 
- `_add(acc: dict, model: str, **kinds: float)` — 
- `claude_code_usage(since: datetime | None, root: Path=CLAUDE_PROJECTS)` — Tokens per Claude model in the Claude Code transcripts (each API call once).
- `hermes_codex_usage(since: datetime | None, home: Path=HERMES_HOME)` — Tokens per model of Hermes sessions billed to the ChatGPT subscription (main + every profile, read-only).
- `codex_cli_usage(since: datetime | None, root: Path=CODEX_SESSIONS)` — Tokens per model of Codex CLI / Codex Desktop sessions (last cumulative token_count of each session).
- `walter_claude_usage(since: datetime | None, sub: dict | None=None)` — Actual model usage of the subscription bridge (not the CLI's synthetic acknowledgement), for one account:
- `usage(sub: dict, since: datetime | None)` — 
- `list_prices(conn)` — $ per million tokens at list API rates (OpenRouter's first-party pricing) per model.
- `priced(acc: dict, prices: dict)` — Totals of a usage dict + its API value; models without a list price are counted but not valued.
- `read_codex()` — Live Codex windows of the owner's ChatGPT account, read with W.Alter's own Codex session (read-only;
- `units(row: dict, weights: dict)` — Meter units of a token row: what moves the Claude meter, cache reads ~free.
- `claude_week_units(sub: dict, now: datetime | None=None)` — 
- `estimate_claude(sub: dict)` — 
- `record(conn, sub_id: str, windows: list[dict], source: str, estimated: bool)` — 
- `refresh(conn, only: str | None=None, min_age_s: float=0)` — Read every meter (or one); skip a meter read less than `min_age_s` ago. A ChatGPT reading carries the
- `calibrate(conn, sub_id: str, weekly_percent: float)` — The owner read the weekly % on claude.ai: capacity = units of the last 7 days / that %. Written to the config.
- `blended(prices: dict, mix: dict)` — $ per million tokens of a model on SemiAnalysis' workload mix.
- `measured_point_value(readings: list[dict])` — API value per meter point from ChatGPT readings of one weekly window (oldest → newest of the window with the
- `state(conn)` — Everything the library shows, per subscription.
- `record_costs(conn)` — Cost price of a token through each plan (owner, 2026-10-22): price / API value carried per month, at the current

## plan/watch.py

Plan research on the web (part of `research plans` and of the 48 h cycle): the economic text tier (L1, Hermes

- `known(conn)` — 
- `parse(text: str)` — The JSON array of the agent's answer (tolerates text or a code fence around it).
- `store(conn, items: list[dict], origin: str='web')` — 
- `run(conn)` — 

## research/__init__.py

Research: everything the router goes and fetches — leaderboards, specialised evaluation sites, provider


## research/agent/__init__.py

The research agent of the 48 h cycle (economic text tier): reads the cycle digest, verifies names on


## research/agent/review.py

Deterministic digest of a refresh cycle, the input of the 48 h analysis agent (economic tier model).

- `_previous_snapshot(conn, kind: str, latest: int)` — 
- `unmatched(conn, limit: int=25)` — Callable models (chat/image/video/audio/music) without any score, next to a scored model with a very similar
- `price_changes(conn)` — Price moves since the previous snapshot of each provider, restricted to the router's short list.
- `digest(conn)` — 

## research/agent/run.py

Step 2 of the 48 h cycle: the research agent, run by Walter Engine (2026-11-13; before, a Hermes loop with shell,

- `prompt(data: dict)` — 
- `parse(text: str | None)` — The agent's JSON object {aliases, report} (tolerates a code fence or text around it); None if absent.
- `apply(conn, aliases: list[dict], add)` — 
- `report_text(day: str, answer: dict | None, added: list[dict], refused: list[dict], raw: str | None)` — 
- `run(conn, *, delegate=None, gather=None, add=None, log_dir: Path | None=None, now: datetime | None=None)` — 

## research/benchmarks/__init__.py

Leaderboards and evaluations, one module per site (fetch only; parsing is analysis.parse).


## research/benchmarks/aa.py

Artificial Analysis Intelligence Index and its cost per task, per model x reasoning level.

- `finite_number(value: Any)` — 
- `decode_rsc_string(encoded: str)` — 
- `strip_rsc_prefix(decoded: str)` — Strip a single-letter RSC flight-stream prefix such as ``c:`` or ``d:``.
- `flight_text(page: str)` — The page's whole flight stream, decoded (a row may span several pushes).
- `leaderboard_models(page: str)` — The `initialModels` array of the leaderboard page: one object per model x reasoning level.
- `task_cost(value: Any)` — Cost per AA task: a number on the leaderboard page, {'cost': {'total': …}} on the older model pages.
- `records(raw_models: list[dict[str, Any]], api: dict[str, dict] | None=None)` — One record per scored model x reasoning level; the API's score wins over the page's, and a model only the
- `api_key()` — The instance's AA key, read from its vault through walter-secrets (host.json `aa_api_key`: item + field).
- `api_scores()` — {slug: {'score', 'name'}} from the free Data API, and an error label when it could not be read.
- `index_version()` — The current Intelligence Index version from AA's methodology page; None when it cannot be read.
- `updates()` — AA's own map of recently changed evaluations ({slug: {'type': 'updated'|'new'|'underReview', 'description',
- `disagreement(raw_models: list[dict[str, Any]], scores: dict[str, dict])` — 
- `source_aa()` — 

## research/benchmarks/aa_decision.py

AA Decision Index (decision models: intelligence, time and cost per 1M tasks).

- `aa_decision_rows(page: str)` — 
- `source_aa_decision()` — 

## research/benchmarks/aa_evaluations.py

Artificial Analysis evaluations and domain indexes, one score per model x reasoning level: specialised domains (medical HealthBench,

- `_objects(page: str)` — Every model object (has a slug and at least one evaluation field) in the page's flight data.
- `_index_models(page: str)` — The initialModels list of an AA index page: weightedIndex, costPerTask.total, timePerTaskSeconds per model.
- `_num(v: Any)` — 
- `merge(objects: list[dict[str, Any]])` — slug -> {name, slug, <key>: value} keeping the first non-null value of each evaluation.
- `source_aa_eval()` — 
- `versions(badges: dict[str, dict], intelligence: str | None)` — Board -> version label (analysis.changes never compares a board across labels): the domain indexes are built

## research/benchmarks/aa_media.py

Artificial Analysis media leaderboards: text-to-speech (provider voice), speech-to-speech, text-to-image,

- `now_iso()` — 
- `normalize_header(value: Any)` — Normalize a rendered table header for robust column matching.
- `clean_cell(value: Any)` — 
- `find_column(headers: list[str], aliases: tuple[str, ...])` — 
- `table_matches(rows: list[list[str]], spec: dict[str, Any])` — 
- `select_task_table(tables: list[list[list[str]]], spec: dict[str, Any])` — 
- `parse_number(value: Any)` — 
- `parse_percent(value: Any)` — 
- `parse_api_price(value: Any)` — 
- `_cell(row: list[str], index: int | None)` — 
- `_elo_rows(spec: dict[str, Any], table_rows: list[list[str]])` — 
- `_speech_to_speech_rows(spec: dict[str, Any], table_rows: list[list[str]])` — 
- `build_task_payload(spec: dict[str, Any], table_rows: list[list[str]], retrieved_at: str)` — 
- `build_multimodal_snapshot(raw_tables: dict[str, list[list[str]]], retrieved_at: str | None=None)` — 
- `source_mm(parts: set[str] | None=None)` — Every module, or only `parts` (module names).

## research/benchmarks/aa_stt.py

AA Speech-to-Text (WER, speed factor, price per model x host).

- `aa_stt_rows(page: str)` — One row per model x host of AA's Speech-to-Text page: the chart download tables (WER vs price, WER vs speed,
- `_host_model_rows(text: str)` — 
- `_table_rows(text: str)` — 
- `source_aa_stt()` — 

## research/benchmarks/agentset.py

Agentset rerankers and embeddings leaderboards (RAG retrieval ELO, latency, price).

- `agentset_board(page: str)` — Leaderboard entries embedded in an Agentset page (rank, name, ELO score, provider, licence, avgLatencyMs,
- `source_agentset()` — 

## research/benchmarks/arena.py

Arena.ai (LMArena) boards, read from the pages' embedded data.

- `_board_matches(key: str, board: dict | None)` — Keep each result attached to the declared public leaderboard identity.
- `arena_board(page: str)` — Leaderboard rows embedded in an Arena.ai page (Next.js flight data): pairwise boards carry 'entries'
- `_close_browser(session: str, *, timeout: float=5)` — Close only the dedicated public collection session, with a bounded wait.
- `_browser_text(url: str, *, timeout: float=BROWSER_TIMEOUT, session: dict | None=None)` — Read a public Arena page via the supported CLI, isolated session, no login or cookie export.
- `source_arena(parts: set[str] | None=None)` — Every board, or only requested keys. A challenged HTTP transport falls back for this collection only.

## research/benchmarks/bridgebench.py

BridgeBench leaderboard (behind Cloudflare: FlareSolverr).

- `bridgebench_rows(page: str)` — Model rows of the BridgeBench leaderboard page: {id, name, vendor, provisional, scores{overall, reasoning,
- `source_bridgebench()` — BridgeBench sits behind a Cloudflare challenge: fetched through the local FlareSolverr.

## research/benchmarks/design_arena.py

Design Arena (designarena.ai) human-preference leaderboards: models arena per design category (website, UI

- `normalize_slug(model_id: str)` — Design Arena ids use dots (gpt-5.6-sol), AA slugs hyphens: lowercase, dots/underscores -> hyphens.
- `leaderboard(category: str, arena_type: str='models')` — 
- `registry()` — 
- `source_da(parts: set[str] | None=None)` — Every category, or only `parts` (category keys; 'agents' = the agents arena).

## research/benchmarks/mteb.py

MTEB results: French retrieval of every embedding model OpenRouter serves.

- `source_mteb()` — MTEB French retrieval (MIRACL-HN fr, nDCG@10) of every embedding model OpenRouter serves that the MTEB results

## research/categories/__init__.py

Research by category (owner, 2026-10-22: « que le sous-module de recherche soit divisé par catégorie pour pouvoir en

- `get(name: str)` — 
- `plan(names: list[str])` — Sources to read for these categories (parts united; None = whole source) and whether plans are refreshed.

## research/categories/audio.py

🎧 Audio and music — Voice and music: AA text-to-speech, speech-to-speech, music (vocals, instrumental), AA speech-to-text.


## research/categories/decision.py

🧭 Decision — Decision models: AA Decision Index (intelligence, time and cost per task).


## research/categories/hosts.py

🏷️ Hosts — The hosts behind OpenRouter for the models in use: price, compression, reliability, speed.


## research/categories/image.py

🖼️ Image — Image generation and editing: AA text-to-image arena, Arena text-to-image and image edit, Design Arena graphic


## research/categories/memory.py

🔎 Memory and search — Embeddings and rerankers: Agentset leaderboards, MTEB French retrieval.


## research/categories/plans.py

💳 Subscriptions — Subscription plans: quota meters and the tokens each plan really carried (cost price per token).


## research/categories/prices.py

💲 Provider prices — Provider catalogues and prices: OpenRouter, Kie, Codex subscription catalogue, OpenAI-compatible providers,


## research/categories/text.py

📝 Text and specialised domains — Text models: AA Intelligence and every AA evaluation / domain index (medical, legal, engineering, finance…),


## research/categories/video.py

🎬 Video — Video generation: AA text-to-video and image-to-video arenas, Arena text-to-video, image-to-video, video edit.


## research/prices/__init__.py

Provider catalogues and prices: OpenRouter, Kie, Codex subscription catalogue, OpenAI-compatible providers, declared offers.


## research/prices/antigravity.py

Google AI Pro through the official Antigravity CLI: the account's model list, as offers the instance qualified.

- `settings()` — Runtime bindings live in the active instance's llm gateway settings.
- `_path(value: str)` — 
- `base_id(cli_id: str)` — Offer key of a CLI id: the reasoning level is a route parameter (same rule as walter-llm's adapter).
- `source_antigravity()` — `agy models` (the CLI's own read of the account); only instance-qualified models become executable offers.

## research/prices/claude_pro.py

Read the subscription catalogue/quota through Walter Secrets' declared grant interface.

- `settings()` — Runtime bindings live in the active instance's llm gateway settings.
- `grant_of(conf: dict, account: str | None)` — The Walter Secrets grant of one Claude account (subscription id), from the gateway's own `accounts` setting.
- `account_json(endpoint: str, account: str | None=None)` — Fixed read-only Anthropic account endpoints; token is never returned in diagnostics. `account` = subscription
- `source_claude_pro()` — Only instance-verified models become executable offers; catalogue presence alone is not validation.
- `read_usage(account: str | None=None)` — Real five-hour/weekly meters of one account, without account identifiers, credit balances or token values.

## research/prices/codex.py

Models of the owner's ChatGPT/Codex subscription, read with W.Alter's own Codex session (2026-11-10: no longer

- `source_codex()` — Live Codex catalogue of the owner's ChatGPT account (read-only; token never printed).

## research/prices/declared.py

Offers no API lists (web UIs, direct keys), declared by the owner.

- `source_declared()` — 

## research/prices/kie.py

Kie.ai market prices.

- `source_kie()` — 

## research/prices/openrouter.py

OpenRouter catalogue, all modalities, media prices from each model page.

- `_or_interface(model: dict)` — 
- `display_pricing(page: str)` — The `displayPricing` array embedded in an OpenRouter model page (per-second / per-song / per-tier prices
- `source_openrouter()` — 

## research/prices/openrouter_endpoints.py

The hosts behind OpenRouter for each model of the active library: price, compression (quantization), reliability

- `_level_fallbacks()` — Models declared as tier fallbacks in the owner's knowledge (levels.*.fallback 'model/variant').
- `watched(conn)` — router model_id -> OpenRouter id, for every model the active library uses or proposes.
- `source_or_endpoints()` — 

## research/prices/providers.py

Live /models of OpenAI-compatible providers configured in Hermes (config/providers.json).

- `source_hermes_providers()` — Live /models catalogue of OpenAI-compatible providers configured in Hermes (config/providers.json).

## research/run.py

`walter-router research [CATEGORY…] [--source KIND] [--list] [--analyse]`: run research now — categories

- `main(args)` — walter-router research [CATEGORY…] [--source KIND] [--list] [--analyse]

## research/sources.py

The source registry: collect every source into models.snapshots (a failing source keeps its last good snapshot), retention.

- `arena_coverage(doc: dict)` — Coverage is distinct from snapshot age: retained boards remain usable, with their failures visible.
- `merge(kind: str, old: dict, new: dict)` — The last complete document with the freshly read parts replacing theirs.
- `collect_all(conn, store, only: list[str] | None=None, parts: dict[str, set | None] | None=None)` — Collect every source (or `only` these kinds, or `parts`: kind -> parts to read, None = whole source); a failing
- `prune(conn, keep_days: int=30)` — Delete snapshots older than keep_days, always keeping the latest one of each kind.

## research/web.py

Web access shared by every source: JSON / pages, FlareSolverr behind Cloudflare challenges, Next.js flight data.

- `now()` — 
- `fetch_json(url: str, payload: dict | None=None)` — 
- `_parse_time(value: str | None)` — 
- `fetch_text(url: str)` — A page, directly; through the local FlareSolverr when the site answers 403/503 (Cloudflare challenge —
- `_json_array(text: str, start: int)` — The JSON array starting at text[start] == '[' (string-aware bracket matching).
- `_json_object(text: str, start: int)` — The JSON object starting at text[start] == '{' (string-aware brace matching).
- `rsc_text(page: str)` — Concatenated Next.js flight payload (self.__next_f.push([1, "..."])) of a server-rendered page.
- `_github_json(url: str)` — 
- `post_json(url: str, payload: dict, attempts: int=4)` — POST a JSON body, polite backoff on rate limits / server errors (crowdsourced APIs such as Design Arena).
- `html_tables(page: str)` — Every top-level <table> of a server-rendered page as rows of cell texts (block children on their own line).

## serve/__init__.py

Serve: what Walter calls at run time — pick a model for a task, understand a request (decision model),


## serve/agent_view.py

What an agent sees of a routing decision: the choice, why, and every execution route with what a million tokens

- `view(d: dict)` — 
- `route_line(e: dict)` — One execution route as the agent needs it: who runs it, and what a million tokens costs there (in / out):

## serve/api.py

Versioned public API descriptions, used by schema output and maintained reference docs.

- `p(kind, description, default=None, **extra)` — 
- `tools()` — 
- `schema()` — 

## serve/brief.py

What an agent must know about Walter Router to use it: what it is for, how to call it, and the parameters that

- `_short(text: str | None)` — First sentence of a role description, without where it runs (« Via Flow… »: the router's business).
- `_tasks(rows: list[dict], interfaces: tuple[str, ...], only: tuple[str, ...]=(), skip: tuple[str, ...]=())` — 
- `_web_quick()` — The intents the owner's rule gives to a web chat service (knowledge.json web_services), as task keys.
- `text(conn, owner: str | None=None)` — Compact operational guidance, independent of current model names, prices and provider choices.
- `document(conn, owner: str | None=None)` — 
- `write(conn)` — Publish both representations from the same producer; keep unchanged bytes stable.

## serve/choose.py

What the router (and the orchestrator) calls: pick the model for a task, the owner's preferences first.

- `latest_run(conn)` — 
- `routes_for(conn, model_id: str, interface: str, modes: list[str] | None=None)` — Every current route for one model: subscription first, then paid routes cheapest first.
- `_pinned_answer(conn, task: dict, pref: dict)` — 
- `_best_score(conn, snaps: dict, boards: list[dict], model_id: str)` — Score on the first board of the task that measures the model (primary first): boards are never mixed,
- `pick_required(conn, t: dict, require: str, limit: int=5)` — Best callable model satisfying a hard constraint (unrestricted / open weights / video input) for a task.
- `pick(conn, task: str, level: str | None=None, role: str | None=None, require: str | None=None)` — The owner's favourite for (task, role) first; otherwise the computed choice for the task's objective.
- `_level_answer(conn, t: dict, level: str | None=None)` — A background text poste (compression, extraction…) follows one of the owner's text tiers — their declared pin for
- `set_preference(conn, task: str, objective: str | None=None, pin: str | None=None, provider: str | None=None, note: str | None=None, role: str='default', watch: str | None=None)` — Record the owner's declaration. Pinning records every current challenger as 'baseline' (no alert for those).

## serve/engine.py

walter_run text jobs executed by Walter Engine (lot E5, 2026-11-10) — no second agent loop in the Router.

- `binding()` — 
- `enabled(d: dict)` — Text jobs go to the engine when the instance says so — a model NAMED by the owner too: the Router validated it
- `unavailable(d: dict, reason: str, detail: str | None=None)` — The structured refusal of a text job the engine cannot take (no binding, engine down): said, never retried by a
- `_token(b: dict)` — 
- `_post(b: dict, body: dict, timeout: float)` — 
- `engine_task(d: dict, spec: dict)` — 
- `run_text(d: dict, spec: dict, *, memory, persist, caller: str='walter_run')` — One delegation to the engine; the result has the shape of the former text path (ok, output, tools…).

## serve/execution.py

Ordered provider routes and execution metadata for Walter consumers.

- `_runnable(offer: dict)` — (Hermes provider, model id at that provider, status key) or None when Hermes cannot run this offer.
- `reliability(conn, provider: str, model: str)` — Recent real executions of this provider x model (models.exec_log, skipped attempts excluded: walter-llm logs a
- `subscription_accounts(conn)` — route provider -> its subscriptions in declaration order, each with its own quota and cost price. Several
- `subscription_costs(conn)` — route provider (codex) -> its first subscription: cost price, plan name, quotas (see subscription_accounts).
- `host_order(conn, model_id: str, usage: str='interactive')` — Usable hosts behind OpenRouter for this model, cheapest first (models.usable_endpoints); flex tier only for
- `routes(conn, model_id: str, variant: str='', preferred: str | None=None, usage: str='interactive', modes: list[str] | None=None)` — Every way Hermes can run this chat model, in the owner's order: subscription (while its weekly quota is not
- `_uuid(value)` — 
- `log(conn, entry: dict)` — One routed execution attempt (from the Hermes plugin or the media executor).
- `_stream_error(data: bytes)` — The provider's own reason when an HTTP 200 stream ends on an error event (Kie: « no_available_account »).
- `_kie_media(kie: str)` — Kie's media API (video, image, music tasks) is another service than its Claude chat API: usable when the
- `_post(url: str, body: dict, headers: dict, timeout: int | None=None, must: str | None=None)` — POST and read the whole answer (SSE included); ok = HTTP 200, non-empty, containing `must` when given
- `probe(conn, only: str | None=None, timeout: int=90)` — Tiny live call per API provider (max 5 output tokens, streamed when the provider streams for Hermes).

## serve/hermes_sync.py

Hermes auxiliary jobs follow Walter Router (2026-10-16, the owner: every W.Alter module that uses AI goes through

- `_wanted(conn, poste: str, level: str | None=None)` — 
- `_aux(home: Path)` — 
- `plan(conn)` — 
- `_plan_home(home: Path, aux: dict, wanted: dict)` — 
- `host_orders(conn)` — OpenRouter model id -> the router's host order (cheapest usable host first) for every OpenRouter route of
- `_routing(home: Path)` — 
- `_plan_routing(conn)` — 
- `_plan_crons(conn)` — 
- `apply(conn, restart: bool=True)` — 

## serve/intent.py

Intent classification by the decision model (OpenRouter's Decisions API, or Cloudflare Workers AI for Clef).

- `chain(conn)` — Decision models to try, in order. The best one comes from the 48 h cycle (task 'decision', AA Decision Index,
- `_cloudflare(model: str, payload: dict, timeout: float)` — Cloudflare Workers AI (Clef family, free daily allocation). Scoped token preferred; the global key only when
- `_nace(model: str, payload: dict, timeout: float)` — Nace systemone (Drex Max): the OpenRouter Decisions contract on Nace's own API (2026-11-13).
- `_criteria(conn)` — 
- `_decisions(conn, state: dict, questions: dict, timeout: float, models: tuple | None=None)` — One Decisions call along the chain (first model that answers) -> (answers, raw answer, ms, errors). Every
- `ask(conn, question: str, options: dict[str, str], context: str | None=None, timeout: float=8.0, models: tuple | None=None)` — The decision model for an agent's own quick choice (sort, yes/no, pick one of several options):
- `classify(conn, request: str, timeout: float=8.0, models: tuple | None=None, context: str | None=None)` — {'task', 'task_confidence', 'video_role', 'role_confidence', 'level', 'unrestricted', 'model', 'cost', 'ms'}.

## serve/media_exec.py

Direct media generation (image, video, music, voice) on the model the router picked.

- `_models()` — 
- `_schemas()` — 
- `_http(method: str, url: str, headers: dict, body: dict | None=None, timeout: int=60)` — 
- `_nearest(value: Any, allowed: list)` — Closest allowed value (case-insensitive for strings, numeric distance for numbers/durations).
- `coerce(path: str, params: dict)` — Keep only the fields the Kie model accepts, mapped to its allowed values (duration, resolution, ratio).
- `craft_prompt(conn, request: str, style: str | None)` — Rewrite the owner's request in the model's prompt style with the economic text tier (L1, walter-llm direct
- `openrouter_id(conn, model_id: str)` — 
- `choose_provider(conn, model_id: str, interface: str, resolution: str | None, has_kie_path: bool, or_id: str | None)` — The owner's order for paid media: Kie if it has the model and is not > 25 % dearer than OpenRouter at this
- `fallback_models(conn, task: str, role: str | None, model_id: str, mode: str | None=None, n: int=2, declared_only: bool=True)` — Other models to try when every provider of `model_id` failed. Since 2026-10-22 (owner: « le secours, c'est pas
- `_kie_key()` — 
- `run_kie(path: str, params: dict, kind: str)` — 
- `run_openrouter(or_id: str, kind: str, params: dict)` — 
- `_download(urls: list[str], b64: list[str], folder: Path, stem: str, auth: dict | None)` — 
- `generate(conn, request: str, task: str | None=None, role: str | None=None, image_urls: list[str] | None=None, aspect_ratio: str | None=None, duration: int | None=None, resolution: str | None=None, paid_fallback: bool=False, craft: bool=True, _depth: int=0, model: str | None=None, _fallback: bool=True, voice: str | None=None, style: str | None=None, provider: str | None=None)` — 

## serve/named.py

A model named by the owner (« avec Opus 5.5 chez Kie ») runs as named, or the answer says why it cannot: never a

- `resolve(conn, name: str)` — (model_id, variant) of a name as the owner or an agent writes it, or None.
- `named(conn, model: str, provider: str | None=None, task: str | None=None)` — The decision for a named model (and provider): its task, and for text the execution routes at that provider

## serve/oneshot.py

One-shot answers for the Router's own needs (lot E6, 2026-11-10: no longer through Hermes).

- `_llm_token()` — 
- `complete(prompt: str, source: str, *, task: str=ECONOMIC, timeout: int=240, max_tokens: int=2000)` — One completion from walter-llm (task = a Router poste; `general/L1` = economic tier). None on any failure.
- `transcribe(path: str, source: str='walter-router', *, task: str='stt', timeout: int=180)` — One audio file → its transcript by the Router's `stt` poste through walter-llm (2026-11-11: the capability
- `delegate(prompt: str, source: str, *, timeout: int=900, task: str='general')` — One task for Walter Engine (Engine API `delegate`): tools, policy and run are the engine's.
- `ask_l1(conn, prompt: str, source: str, timeout: int=240, tools: str='memory', max_turns: int=1)` — Former Hermes one-shot, same signature: no tool use → economical direct path; tools (web…) → the engine.

## serve/routes.py

Ordered providers of the selected model, media provider routes, service poste ids and the free-text entry.

- `with_execution(conn, out: dict)` — Add the selected model's ordered providers; availability never authorises another model.
- `route(conn, request: str, task: str | None=None, level: str | None=None, context: str | None=None, web_rules: bool=True)` — Free-text request -> intent by the decision model (task, video role, level, unrestricted) -> decision + routes.

## serve/run.py

Do the job on the chosen model — one entry for every runtime (Hermes plugin, walter MCP, the command).

- `default_toolsets()` — 
- `_memory(action: str, payload: dict)` — Walter Memory's Run Plane through its command (declared interface); never blocks the sub-agent.
- `_persist_observations(output: str, run_id: str | None, task_id: str | None, geo: dict | None)` — persist="observations": the answer's "observations" list becomes sourced observations of the run (Walter
- `decide(conn, spec: dict)` — 
- `_web(conn, d: dict, spec: dict)` — The owner's rule gave this intent to a web chat service: the user's own words go there (the request, else the
- `_run(conn, spec: dict)` — 
- `_dispatch(conn, d: dict, spec: dict)` — 
- `run(conn, spec: dict)` — Versioned result; existing fields remain compatible with every current adapter.

## serve/web.py

Conversational web services as a Router tool (walter_web): a message, optional files and model, the reply verbatim.

- `out_dir()` — Same place as the router's generated media (the agents already look there).
- `converse(spec: dict)` — 
- `_enabled()` — Services the gateway has enabled (its own rule table, the owner's switch).
- `commands()` — Chat command → web service, from the gateway's rule table (`/gpt` → chatgpt…), for the Telegram door.
- `route_for(task: str | None, level: str | None)` — The web service the owner's rule gives this classified intent, or None.

## store/__init__.py

Store: the router's database (schema models in PostgreSQL): connection, migrations, maintenance.


## store/db.py

Connection handling. Credentials come from ~/.pgpass (never from code or DSNs).

- `connect()` — 
- `migrate()` — Apply every migrations/NNN_*.sql not yet recorded in models.schema_migrations (each file is one transaction).

