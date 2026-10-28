# walter-lab

Measured experiments on Walter itself (P6, 2026-10-28). Lab asks “is there a better way?” where a Guardian asks “does
it work?” and the Curator organises skills — no overlap (owner decisions, 2026-10-27). An experiment compares variants
on the shared end-to-end bench (`walter-scenario`), interleaved, with its decision rule written before the runs; it may
conclude that nothing should change, and it never applies anything.

Experiment v1: see `walter_lab/core.py` and `experiments/`. Reports: `@instance/state/lab/<experiment>/<time>.json`.
Not built yet (by design, next steps): a scout of external sources, and a sandbox without secrets nor production data
for any external code — required before an experiment may run it. The first planned comparison of runtimes (DSH, Pi,
Hermes) needs that sandbox and a runtime-neutral scenario step.
