---
name: memory-context-quality-validation
description: Use when validating changes to Walter Memory extraction, working state, reconsolidation, or Walter Context selection before enabling injection.
---

## Prepare an isolated, reproducible comparison

- Read the memory architecture and dated decisions before changing behavior. Resolve module locations with `walter path memory` and `walter path context`; `/walter/cognition/memory` and `/walter/cognition/context` were the locations verified in this session.
- Back up affected code and database schemas under the instance's `backups/changes/` directory. Preserve a rollback script alongside the backup before applying a migration.
- Use a disposable PostgreSQL database for quality experiments. The session used container `walter-memory-testpg`, exposed on port 5440; production used `hindsight-pg` on port 5433. Verify these live before running anything. Never reset benchmark state against production.
- Supply `WALTER_MEMORY_DATABASE_URL` through the approved secret mechanism; never print it or embed credentials in commands, reports, or skills.
- Preserve the same reference corpus when comparing policies. The session used 12 threads and 68 reference items; retain the corpus and output artifacts so later results are comparable.

## Run and inspect the quality bench

From the resolved Memory module directory, with the disposable database environment already configured:

```bash
walter-python bench/memory_v1.py /path/to/reference.jsonl /path/to/results-directory
```

- Inspect the script's current arguments before reuse. Preserve `results.json` and `disagreements.json` when produced.
- Measure four separate levels: availability in raw events/search, presence in working state, selection after the Context budget, and final interpretation. Report each denominator. A retrieval success does not prove that Context selected the information or that extraction represented the whole request.
- Inspect missing items individually. Distinguish information never extracted from information present in state but omitted by selection.
- Treat a message as grounded interpretation only when a retained knowledge item cites it. Even then, inspect coverage: one cited fragment can leave the rest of a multi-part request unrepresented.
- When working state deliberately includes the latest message, distinguish that entry from messages awaiting interpretation. Tests asserting an empty pending list must account for entries marked `last`.

## Validate annotations independently

- Have a second annotator examine the source threads without seeing the original annotations.
- Preserve original references, additional candidates, disagreements, and both judges' outputs. Do not automatically treat the second annotator's additions as ground truth.
- Prepare a human arbitration artifact for ambiguous or implicit candidates before claiming an improved reference score.
- During slow runs, inspect the output log, process tree, and disposable database activity. For example:

```bash
docker exec walter-memory-testpg psql -U hindsight -d hindsight -Atc 'select processor, count(*) from system.model_calls group by 1'
```

## Evaluate reconsolidation separately

- Preserve proposed merges, supersessions, expirations, and their evidence before applying them.
- Exercise the proposal-only interface first: `consolidate.reconsolidate(subject, apply=False)`.
- Test the configured Router tier on representative subjects. In this session, reconsolidation quality required moving beyond the extraction route; configure a Router poste rather than hardcoding a provider model.
- Distinguish completed goals or decisions from expired rules. Guard destructive proposals by item kind and scope in code; prompt instructions alone are insufficient.
- When remeasuring reconsolidation, reset only the disposable benchmark state. The session added `bench/p12_recon.py` for this purpose; inspect its current arguments before reuse.

## Gate activation on quality and runtime checks

- Keep new generations in shadow mode while comparing them with the active generation. Verify shadow output is not injected into Context.
- Run the relevant Memory and Context tests after the final changes. Preserve quality measurements separately from unit-test results.
- Verify evidence links and database-enforced privacy behavior on generated views.
- Reload the pipeline only after validation, then inspect `systemctl is-active walter-memory-pipeline` and its journal. Follow the VM rule to run `systemctl start memory-autopilot` after memory service changes and inspect its score.
- Record the active generation, shadow modes, injection status, migrations, rollback location, quality limitations, and activation decision. Passing tests alone does not establish recall quality.
