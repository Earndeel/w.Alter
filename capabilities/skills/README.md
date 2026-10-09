# walter-skills

W.Alter's procedural memory (skills and workflows), independent of the runtime. Hermes, Claude Code, Codex and DSH
are only clients. Plan: `/root/.hermes/docs/walter-memory/PLAN.md` (P10). Decisions: `DECISIONS.md` (2026-10-09).

Status: benchmark only. The store, the `skills` schema, retrieval, injection and the curator are still to come.

## Benchmark (`bench/`)
- `build_dataset.py`: builds the cases from `walter_logs`. Each case is a user message plus the previous turn,
  paired with the skills Hermes opened before the next message. Writes `bench/data/` (0600, private messages,
  never committed).
- `evaluate.py`: local retrievers. Metrics: hit@1, hit@3, hit@10, MRR and latency, on two corpora: `full` (active +
  archived skills) and `active` (gold mapped through the curator's absorption chain).
- `hermes_llm.py`: Hermes baseline. An LLM reads Hermes' skill index and picks skills. Calls go through
  `walter_memory.llm` (budget `backfill`; `local_only` messages are excluded).

```
/opt/walter-memory/venv/bin/python bench/build_dataset.py
/opt/walter-memory/venv/bin/python bench/hermes_llm.py --corpus active --dev 100
/opt/walter-memory/venv/bin/python bench/evaluate.py --ids-from bench/data/llm_active_hermes-index_gpt-6-luna.jsonl
```
