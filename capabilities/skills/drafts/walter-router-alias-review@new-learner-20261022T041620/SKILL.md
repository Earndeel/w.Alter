---
name: walter-router-alias-review
description: Use when reviewing a Walter Router collection cycle and reconciling model names across sources through the approved alias-add command.
---

# Review model-name mismatches

## Establish the scope and current state

Respect the cycle request's write restrictions. When only alias corrections are authorized, do not modify configuration, project files, prices, routes, tiers, or database rows directly. Do not launch collection or refresh jobs.

Use the public `walter-router` command on PATH. Read:

```sh
walter-router review
walter-router health
walter-router alias-list
walter-router alias-add --help
```

Inspect source freshness, provider health, computed versus declared tiers, shortlist price changes, and `unmatched_candidates`. Use `walter-router dossier TASK` for a candidate's task context and `walter-router library --json` for catalog entries.

## Handle JSON and tool-output failures

Inspect JSON shape before filtering. The observed `library --json` result was a list of objects; calling `.lower()` on its elements raised `AttributeError`. Inspect object keys and search string fields explicitly.

If a tool labels a command result as an error, inspect its exit code and actual output before concluding the CLI failed. This session included error-labelled results with exit code 0 and valid help text. If output is missing, capture stdout and stderr once and print a bounded structural summary instead of repeatedly issuing the same large command:

```python
import json
import subprocess

p = subprocess.run(
    ['walter-router', 'review'],
    capture_output=True, text=True, check=True,
)
d = json.loads(p.stdout)
print(type(d).__name__)
print(list(d) if isinstance(d, dict) else len(d))
print(json.dumps(d.get('unmatched_candidates', []), ensure_ascii=False))
```

## Verify identity before adding an alias

Treat unmatched candidates as hypotheses. Verify the exact version, size, variant, modality, and provider identity against catalog data and authoritative model documentation. A spelling resemblance or added `v` is insufficient evidence alone. Preserve distinctions such as Lite versus Pro, vector versus raster, and different model generations. Leave uncertain candidates unresolved.

Record the evidence URL or catalog evidence in the reason. Do not use search snippets as conclusive identity proof. If extraction is unavailable or blocked, use an available approved retrieval mechanism or leave the candidate pending.

## Apply and verify individually

The validated CLI syntax is:

```sh
walter-router alias-add 'SOURCE_KEY' 'CANONICAL_MODEL_ID' --reason 'Verified identity and supporting evidence'
```

Check each command's result before applying another alias. Then run:

```sh
walter-router alias-list
walter-router review
walter-router health
```

Confirm the alias maps to the intended canonical ID and inspect remaining mismatches. Do not assume alias insertion refreshes collected snapshots, recalculates all derived results, or changes routes. Report confirmed corrections, unresolved identities, and observed health separately. Write a report file only when the task authorizes it.
