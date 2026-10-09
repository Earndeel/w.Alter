# Recall Benchmarking Methodology (Hindsight)

How to measure retrieval quality objectively instead of arguing from impressions.
Companion script: `/root/.hermes/scripts/recall_bench.py` — per-run JSON in `/root/.hermes/membench/`.

## Panel design (14 probes, 5 categories)

| Category | What it tests | Example |
|---|---|---|
| dure | Explicit rules known to exist, queried near-verbatim | vouvoiement/tone, URL format, cost policy |
| semantique | Same knowledge, paraphrased with NO shared keywords | "comment l'assistant doit-il me parler" → tone rules |
| bruit | Queries that used to surface ephemeral run logs | proc_ ids, "N/N tests", durations |
| negatif | Out-of-domain nonsense | coq au vin recipe, PSG score |

Each probe carries: hit keywords (expected fact) and pollute keywords (known-bad facts). Run modes: `baseline` / `after`, output diffable JSON.

## Judge pitfalls (learned 2026-08-21)

- **Keyword-presence judges produce false negatives.** P03 failed the judge while the correct fact sat at rank 1 — the fact used synonyms ("hiérarchie d'outils… walter_browse") outside my keyword list. ALWAYS eyeball top-3 before declaring a probe failed.
- **Negative probes can't be scored by keyword absence.** Anything tech-vocabulary matches something. Treat them as qualitative: record result count (expect >0, see quota-fill below) and whether top hits are at least topically adjacent.
- Keep probes byte-stable across runs; never regenerate wording between baseline and after.

## Measured findings on this stack (walter bank, 2026-08-21)

- **Score bands are flat: ~0.67–0.82 regardless of true relevance.** A perfect durable rule scored 0.72; narrative noise scored 0.69. Consequence: ABSOLUTE SCORE THRESHOLDS ARE NOT VIABLE as injection filters here. Don't re-attempt min_score gating; filter by type/tags/dedup instead.
- **The engine fills its quota unconditionally.** A 3-word query returned 33 facts; absurd queries return 20+. There is no server-side abstention ("je ne sais pas") mechanism — this is architectural, not a tunable.
- **Corpus hygiene dominates ranking quality.** Purging 408 ephemeral facts fixed the polluted probes; no ranker tuning could have. Fix the corpus before touching the retriever.
- **Verify 8889 freshness before benchmarking it.** Until the units_qdrant_sync port, the hybrid index was frozen at July data and would silently skew any measurement. Sanity-check with a same-day fact.

## Operational patterns that worked

- **Purge with reversible archive**: dump matched rows to JSON (`membench/purge_archive.json`) before deleting; dry-run flag mandatory first run.
- **Bulk, never per-item shells**: load ALL PG texts once into a Python set for dedup/orphan scans. A docker-exec-per-point loop (7.6k iterations) blows foreground timeouts.
- **Zero-cost vector sync**: pgvector stores the embedding already — cast `embedding::text` to a JSON array and upsert to Qdrant named vector `dense`. No embedding API calls needed.
- **systemd drop-in overrides**: `mkdir -p /etc/systemd/system/<svc>.service.d` BEFORE writing override.conf, else the redirect fails silently-ish and the old ExecStart keeps running.
