# Walter Router — data reference (2026-10-17)


> Référence SQL exhaustive actuelle : [reference/DATABASE.md](reference/DATABASE.md) (toutes les colonnes, types, défauts, contraintes, index et vues). Ce guide explique la provenance. Les déclarations/configurations d’instance et les secrets ne sont pas tous dans PG ; voir OPERATIONS.md.

The structured catalogue, measurements and derived decisions live in schema `models` of Postgres `hindsight-pg` (127.0.0.1:5433, db `hindsight`,
password only in `~/.pgpass`). Python access: `walter_router.store.db.connect()`. Each table and view also carries a
`COMMENT` (`store/migrations/022_comments.sql`): `\d+ models.*` explains itself.

Writes go through the router code only (`walter-router refresh`, `declare`, `prefer`, `verdict`, `feedback`,
`log-exec`, plus walter-llm, which logs into `exec_log`). Nothing else writes `models.*`.

## 1. Sources → `snapshots`
One row per fetch (`kind`, `fetched_at`, `source_url`, `sha256`, `row_count`, `raw` = the document as fetched).
The same content is never stored twice; 30-day retention; the latest snapshot of each kind is always kept, and a
failing source keeps its last good one (view `latest_snapshots`). Freshness: `walter-router health` →
`sources_age_h` (the cycle runs every 48 h; a board missing from a snapshot raises a `board_down` alert).

| kind | What | Where from |
|---|---|---|
| `aa` | AA Intelligence Index + cost per AA task, per model × reasoning level; the snapshot carries `index_version` (rows: `extra.index_version`), and the board is never compared across versions | artificialanalysis.ai models leaderboard (Next.js flight data: score, cost per task, list prices) + free Data API (score; key = host.json `aa_api_key`, read through walter-secrets) + methodology page (version), `research/benchmarks/aa.py` |
| `aa_eval` | AA evaluations per model × level (benchmark `aa_eval`, task = evaluation): HealthBench / HealthBench Professional (medical), Harvey LAB (legal), τ³-Banking, CritPt, GPQA, SciCode, HLE (science), MMMU-Pro (vision), AA-3D (Elo), AA-LCR (long context), IFBench, τ², Terminal-Bench Hard, GDPval, APEX-Agents, Omniscience, LiveCodeBench, Cyber Index; and the AA domain indexes `idx_engineering`, `idx_economics`, `idx_finance`, `idx_medical`, `idx_legal`, `idx_strategy_ops` (score + cost per task); fractions stored ×100 | AA model page + HealthBench, Cyber and /indexes pages (Next.js data), `research/benchmarks/aa_evaluations.py` |
| `mm` | AA multimodal arenas: text-to-image, text-to-video, image-to-video, TTS, speech-to-speech, music (vocals, instrumental) | artificialanalysis.ai leaderboard tables, `research/benchmarks/aa_media.py` |
| `da` | Design Arena: models (website, UI component, 3D, game, dataviz, SVG, logo, graphic design…) and agents (full-stack, mobile, native apps) | designarena.ai JSON API, `research/benchmarks/design_arena.py` |
| `arena` | Arena.ai (LMArena), 15 boards: text, French, coding, creative, webdev, vision, document, search, agent, text-to-image, image edit, text-to-video, image-to-video, video edit, image-to-webdev | arena.ai/leaderboard/… (embedded page data; FlareSolverr on 403/503) |
| `bridgebench` | BridgeBench: overall, backend, frontend, reasoning, security, speed, trustworthiness, efficiency, one-shot, cost | bridgebench.ai/leaderboard (through FlareSolverr 127.0.0.1:8191) |
| `aa_decision` | AA Decision Index v1 (intelligence, time and cost per 1M tasks) for decision models | artificialanalysis.ai/evaluations/artificial-analysis-decision-index |
| `aa_stt` | AA Speech-to-Text: WER, speed factor, price per 1000 min, per model × host | artificialanalysis.ai/speech-to-text |
| `agentset` | Rerankers and embeddings: ELO on RAG retrieval, latency, nDCG@10, price | agentset.ai/rerankers, /embeddings |
| `mteb` | MIRACL French retrieval nDCG@10 for every embedding model OpenRouter serves | github.com/embeddings-benchmark/results |
| `or_endpoints` | The hosts behind OpenRouter for each model of the active library: price, quantization, service tier (flex / priority), uptime 24 h / 30 min, latency, tools | openrouter.ai/api/v1/models/<id>/endpoints, `research/prices/openrouter_endpoints.py` |
| `openrouter` | Every OpenRouter model, all modalities, prices (media prices from each model page's `displayPricing`) | openrouter.ai/api/v1/models |
| `kie` | Kie.ai market prices (credits → $) | api.kie.ai/client/v1/model-pricing |
| `codex` | Models of W.Alter's ChatGPT/Codex subscription | read through Hermes (no price: subscription) |
| `hermes_providers` | Live `/models` of OpenAI-compatible providers configured in Hermes (`config/providers.json`, today Arnict) | provider API, key through Walter Secrets (card `[env]` of the provider's grant, reader `router`) sent as a header |
| `declared` | Offers no API lists (web UIs, direct keys), declared by the owner | `config/declared_offers.json` |

## 2. Identity
| Table | Content |
|---|---|
| `canonical` | One row per model: `model_id` (normalised), vendor, display name, open weights / licence, `content_policy` (`unrestricted` + `base_model_id` for uncensored fine-tunes), context length |
| `aliases` | `(namespace, external_key) → model_id` per source; `origin` = auto / manual (`aliases.json`, validated `alias-add` with evidence) / agent |

Unmatched names are listed by `walter-router review` (`unmatched_candidates`) for the 48 h analysis agent.

## 3. Measurements and offers (one row per snapshot)
| Table | Content |
|---|---|
| `benchmarks` | Measured quality: `benchmark` (board family: `aa_intelligence`, `aa_mm`, `arena`, `da_models`, `da_agents`, `bridgebench`, `aa_decision`, `aa_stt`, `agentset`, `mteb`), `task` (sub-board), `model_id`, `variant` (reasoning level), `score` (**always higher = better**: WER → 100 − WER, latency → 1000/ms), `cost` (the board's own published cost, e.g. AA $ per task), `extra` (votes, CI, raw measures) |
| `offers` | Callable and priced: `provider`, `offer_key`, `interface` (chat, image, video, audio, music, transcription, embedding, rerank, decisions…), `access` (paid / subscription / ui / free), `price_in_1m`/`price_out_1m` ($/M tokens) or `unit_price`+`unit`, media classification (`offer_kind`, `modes` t2i/i2i/t2v/i2v/r2v/v2v, `resolution`, `audio`); for chat and decision offers `modes` = the inputs the model reads besides text (image, audio, video, file — OpenRouter only: other providers do not declare them; `--require video_input` keeps the models and routes that read video), `norm_price`/`norm_unit` (video per second, image per image, voice per 1000 characters, STT per minute) |
| `endpoints` | One row per host behind a gateway per snapshot (`or_endpoints`). Views `usable_endpoints` (>= 95 % uptime 24 h, not below the vendor's own precision) and `best_endpoints` (cheapest per model, `usage` interactive = no flex tier / background = flex allowed) |
| `provider_status` | Last 5-token live probe per provider (`probe`), OpenRouter credit in `detail` |

## 4. Tasks and the owner's knowledge
| Table | Content | Written by |
|---|---|---|
| `tasks` | The 42 tasks: label, `interface`, `default_objective`, `intent_hint` (for the classifier), `internal` (module postes never offered to the classifier), `modes` (generation modes of a media task; for a chat task the inputs every route must read — none today), `requirements`, `consumers` | migrations + `declare` |
| `task_benchmarks` | Which boards rank a task and their **weights** (`weight`, `is_primary`) — shown on the library page under each task | migrations |
| `preferences` | the owner's choices per task / role: objective (`best_available`, `value`, `level`), pin (model, variant, provider), role label/description/signals (video roles), `watch` | `knowledge.json` via `declare`, `prefer`, `verdict` |
| `profiles` | What a model is *for*: strengths, weaknesses, workflow, effort, access / cost notes | `knowledge.json` |
| `affinities` | Close calls: the owner's preferred model inside the tie margin | `knowledge.json` |
| `feedback` | the owner's verdicts on a model (−2..2, ±3 composite points each, capped ±9) | `feedback`, tool `walter_feedback` |

## 5. Computed every refresh (one `run_id` per refresh)
| Table / view | Content |
|---|---|
| `runs` | Each refresh: status, summary JSON (sources, changes, alerts, notifications) — view `latest_run` |
| `selection` | Per task × level (`best`, `value`, `L1`–`L3`, `frontier`…) × rank: model, variant, quality, real cost, provider, offer, subscription, `reasons` |
| `dossiers` | One JSON per task: boards and weights, roles, top candidates with per-board evidence, routes, prices, picks, rules — view `latest_dossiers`, `walter-router dossier <task>` |
| `alerts` | `challenger`, `new_best`, `tier`, `nerf`, `pareto`, `board_down`, `top3`, `unranked` (recorded, never sent), `billing` with `evidence` (and the stored recommendation `evidence.reco`), `status` open / adopted / dismissed, `notified_at` |

## 6. Execution and usage
| Table / view | Content |
|---|---|
| `exec_log` | Every routed attempt (walter_run, generate, walter-llm): task, provider, model, ok, seconds, cost. A provider × model failing ≥ 50 % of its last ≥ 3 runs in 14 days goes last |
| `plan_evidence` | Facts about plans with their source: web research, billing mails (origin email, deterministic), measures, the owner |
| `subscription_costs` | Cost price of a token through each plan: price / API value carried per month (pace, capacity), ratios, meter — view `latest_subscription_costs` |
| `subscription_usage` | Quota readings of the subscriptions (ChatGPT Plus real, Claude Pro estimated) — view `latest_subscription_usage` |

## 7. Views for reading
| View | Use |
|---|---|
| `catalog` | One row per model × interface: modes, providers, price range, resolutions, release, every leaderboard score, open weights, content policy |
| `open_models` | Open-weight and unrestricted models (with scores inherited from the base model, flagged) |
| `model_scores` | All scores of a model in one JSON |
| `shortlist` | Models currently selected for some task / level (why = « top level #rank ») — the price-change watch list |

## 8. Common questions
```sql
-- what does the router use for each task right now (same as the library page)
select task, level, model_id, variant, provider, real_cost, cost_unit from models.selection
 where run_id = (select run_id from models.latest_run) and rank = 1 order by task, level;
-- the boards behind a task and their weights
select benchmark, bench_task, weight, is_primary from models.task_benchmarks where task = 'text_to_video';
-- every price of a model, all providers (latest snapshots)
select provider, interface, price_in_1m, price_out_1m, unit_price, unit, norm_price, norm_unit from models.offers
 where model_id = 'minimax-h3' and snapshot_id in (select snapshot_id from models.latest_snapshots);
-- has a model failed lately
select at, task, provider, model, ok, seconds from models.exec_log where model_id = 'gpt-6-luna' order by at desc limit 20;
```
CLI equivalents: `walter-router library` (the full table), `pick <task>`, `dossier <task>`, `status`, `health`,
`alerts`, `review`. Web: https://the instance library domain (host.json library_domain) (English) and /fr/.

## 9. Collecting by hand
`walter-router research [CATEGORY …] [--analyse]` (categories: text, image, video, audio, memory, decision, prices,
hosts, plans) or `walter-router research --source KIND …` fetches sources now (all, or the given kinds: `aa`, `aa_eval`, `mm`, `da`,
`arena`, `bridgebench`, `aa_decision`, `aa_stt`, `agentset`, `mteb`, `openrouter`, `kie`, `codex`, `declared`,
`hermes_providers`), stores and understands them; then `walter-router refresh --skip-collect` recomputes the choices.
