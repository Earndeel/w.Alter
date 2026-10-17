-- Self-describing schema (Monsieur, 2026-10-17: « que tout soit bien documenté »). Reference: docs/DATA.md.
comment on schema models is 'Walter Router: model catalogue, leaderboards, prices, providers and per-task choice. Written only by /opt/walter-router (and walter-llm into exec_log). Reference: /opt/walter-router/docs/DATA.md';

comment on table models.snapshots is 'One fetch of a source (kind = aa, mm, da, arena, bridgebench, aa_decision, aa_stt, agentset, mteb, openrouter, kie, codex, hermes_providers, declared); raw document kept, deduplicated by sha256, 30-day retention, latest per kind always kept';
comment on table models.canonical is 'One row per model (normalised model_id): vendor, display name, open weights / licence, content_policy (unrestricted + base_model_id), context length';
comment on table models.aliases is 'Source name -> model_id per namespace; origin auto / manual (aliases.json, alias-add with evidence) / agent';
comment on table models.benchmarks is 'Measured quality per snapshot: benchmark family, task (sub-board), model_id, variant (reasoning level), score (always higher = better), cost (board-published, e.g. AA $ per task), extra (votes, CI, raw measures)';
comment on table models.offers is 'Callable, priced offers per snapshot: provider, interface, access (paid/subscription/ui/free), $/M tokens or unit price, media modes/resolution/audio, normalised price (per second, image, 1000 chars, minute)';
comment on table models.provider_status is 'Last live 5-token probe per provider (OpenRouter credit in detail); a failed provider goes last in routes';
comment on table models.tasks is 'Router tasks: interface, default objective, intent_hint for the classifier, internal (module postes never offered to the classifier), requirements, consumers';
comment on table models.task_benchmarks is 'Boards that rank each task and their weights (scoring.composite); shown under each task on the library page';
comment on table models.preferences is 'Monsieur''s choices per task / role: objective, pinned model/variant/provider, role label, description and signals, watch. A change of favourite only through his verdict';
comment on table models.profiles is 'What a model is for (knowledge.json): strengths, weaknesses, workflow, effort, access and cost notes';
comment on table models.affinities is 'Close calls: Monsieur''s preferred model inside the tie margin (knowledge.json)';
comment on table models.feedback is 'Monsieur''s verdicts on a model (-2..2), +/-3 composite points each, capped +/-9';
comment on table models.runs is 'One row per refresh: status and summary (sources, changes, alerts, notifications)';
comment on table models.selection is 'Per refresh, task, level (best, value, L1-L3, frontier...) and rank: chosen model, variant, quality, real cost, provider, offer, subscription, reasons';
comment on table models.dossiers is 'Per refresh and task: the JSON the router reads (boards and weights, roles, candidates with per-board evidence, routes, prices, rules)';
comment on table models.alerts is 'challenger, new_best, tier, nerf, pareto, board_down, top3, unranked, billing; evidence (+ stored recommendation evidence.reco), status open/adopted/dismissed. Telegram proposals with buttons; never an automatic switch';
comment on table models.exec_log is 'Every routed execution attempt (walter_run, generate, walter-llm): provider, model, ok, seconds, cost. >= 50 % failures over >= 3 runs in 14 days demotes the route';
comment on table models.subscription_usage is 'Subscription quota readings (ChatGPT Plus real via Codex, Claude Pro estimated from Claude Code transcripts); information only';
comment on table models.schema_migrations is 'Applied migrations of /opt/walter-router/migrations';

comment on view models.latest_snapshots is 'Latest snapshot id per source kind';
comment on view models.latest_run is 'Latest successful refresh run id';
comment on view models.latest_dossiers is 'Dossier of each task from the latest run';
comment on view models.latest_subscription_usage is 'Latest quota reading per subscription and window';
comment on view models.catalog is 'One row per model and interface: modes, providers, price range, resolutions, release date, every leaderboard score, open weights, content policy';
comment on view models.open_models is 'Open-weight and unrestricted models, scores inherited from the base model flagged';
comment on view models.model_scores is 'All latest scores of a model as one JSON (benchmark:task -> score)';
comment on view models.shortlist is 'Models currently selected for some task / level: the price-change watch list';
