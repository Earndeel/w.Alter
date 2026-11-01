# Digest & surface reproduction harness

Concrete, reusable probes from a Walter Operator Lot 2.2 Reviewer-B catch-up. Generalize the
path/names to your case. The core lesson: **a claimed SHA or surface-equivalence is only
verified when you recompute it yourself under the real runtime.**

## A. Brute-force the JSON serialization convention to reproduce a claimed SHA

Given a claimed `sha256` and the object it supposedly hashes (or candidate objects), sweep
serialization knobs in one script. Reported which conventions hit:

```python
import hashlib, json

target = "7cdbe7c135d1c763ad4534fec7e8dcac53d0391e6cf9648afd31b8c302c6e3dd"

def H(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()

def sweep(label, obj):
    cands = {
        "sort ascii=T":  json.dumps(obj, sort_keys=True,  ensure_ascii=True),
        "sort ascii=F":  json.dumps(obj, sort_keys=True,  ensure_ascii=False),
        "nosort ascii=T":json.dumps(obj, sort_keys=False, ensure_ascii=True),
        "compact sort T":json.dumps(obj, sort_keys=True,  separators=(',',':'), ensure_ascii=True),
        "compact nosort F":json.dumps(obj, sort_keys=False, separators=(',',':'), ensure_ascii=False),
    }
    for k, s in cands.items():
        if H(s) == target: print("MATCH", label, k)
        if H(s + "\n") == target: print("MATCH", label, k, "+newline")
```

Findings from the real case:
- The "raw schema" digest was **sha256 of the compact, sort_keys, ensure_ascii=True JSON of the
  *merged* full model-facing schema** (base `COMPUTER_USE_SCHEMA` with the plugin's dynamic
  `parameters` applied): `json.dumps(full_schema, sort_keys=True, separators=(',',':'), ensure_ascii=True)`.
  The plain (spaced-separator) dumps did NOT match.
- The "override" digest used a different, undocumented convention that resisted every sweep.
  Because content equality was proven separately (the stored `overrides` dict deep-equals the
  object the runtime produces), the claim still held; the unreproducible convention became a
  should-fix documentation gap, NOT a failed finding.

Takeaway: digest equality for BOTH sides is the invariant that matters most; matching one exact
convention is a bonus. Prove content equality when a convention won't reproduce, and downgrade
the convention gap to a doc nit.

## B. Isolated-HERMES_HOME surface comparison (two plugin versions, same runtime)

Prove V1.1 vs V1.2 register a byte-identical model-facing surface under the *certified* release:

1. Two `tempfile.TemporaryDirectory()` HERMES_HOME dirs. Into each write a minimal config that
   enables exactly the plugin under test (without this the plugin is discovered but
   `"not enabled in config"` → `enabled:false` with an error):
   ```yaml
   plugins:
     enabled:
       - walter-computer-use
     disabled: []
   ```
2. `shutil.copytree(<installed-version-dir>, <home>/plugins/<name>)` for side A and the
   candidate dir for side B.
3. Run under the certified release venv from the release root so its packages import:
   ```
   <release>/venv/bin/python -c '<snippet>'   # cwd=<release>, env HERMES_HOME=<side-X>
   ```
   Snippet imports, discovers plugins, then reads live registries and digests:
   ```python
   import os, hashlib, json, sys
   os.environ.setdefault("HERMES_COMPUTER_USE_BACKEND", "walter")
   from hermes_cli.plugins import discover_plugins, get_plugin_manager
   from tools.computer_use.backend import registered_action_extensions, registered_backend_names
   from tools.computer_use.tool import _computer_use_schema_overrides
   from tools.computer_use.schema import COMPUTER_USE_SCHEMA
   discover_plugins(force=True)
   ov = _computer_use_schema_overrides()
   full = json.loads(json.dumps(dict(COMPUTER_USE_SCHEMA))); full["parameters"] = ov["parameters"]
   sha = lambda o: hashlib.sha256(json.dumps(o, sort_keys=True, separators=(',',':'),
                                             ensure_ascii=True).encode()).hexdigest()
   print(json.dumps({
     "registered_backends": sorted(registered_backend_names()),
     "registered_actions": sorted(e.name for e in registered_action_extensions()),
     "action_enum": (ov["parameters"]["properties"].get("action") or {}).get("enum", []),
     "goal_property": ov["parameters"]["properties"].get("goal"),
     "override_sha": sha(ov),
     "raw_schema_sha": sha(full),
   }, sort_keys=True))
   ```
4. `surfaces_equal = True` only if every compared field (backends, actions, tool_name,
   action_enum, goal_property, both digests) is identical across the two sides. The plugin
   `version` string WILL differ between V1.1 and V1.2 — exclude it from the equality check.

## C. Artifact-vs-generator field-drift check

The shipped benchmark artifact must be produced by the committed generator.
- Dump both key sets and diff:
  `python3 -c "import json;print(sorted(json.load(open('artifact.json'))['native_refs']))"`
  vs. reading the generator's dict literal.
- `grep -rn "stale_ref_incorrectly_accepted" .` → found ONLY in the artifact and nowhere in
  code means the artifact predates a rename (this real case: generator now emits
  `exact_sequence_failures` + `stale_status_contract`; the stale artifact still carried the old
  `stale_ref_incorrectly_accepted` and was MISSING the two new keys).
- Confirm with the repo's own test: a committed `test_*_report.py` asserting those keys fails
  deterministically (`KeyError: 'exact_sequence_failures'`). Full-suite result then contradicts
  the doc's "N passed" gate (real case: claimed 133 passed; actual 135 collected → 134/1 failed).
