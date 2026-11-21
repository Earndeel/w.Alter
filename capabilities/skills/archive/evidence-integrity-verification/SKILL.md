---
name: evidence-integrity-verification
description: Verify review evidence by reproduction, not trust.
---

# Evidence-Integrity Verification

How to independently verify a release candidate's data-integrity evidence instead of trusting
the shipped artifact or a reviewer's conclusion. Born from a Reviewer-B catch-up where the
previous reviewer blocked on a **false positive** because it compared against the wrong tree,
and where a separate **real** data-integrity defect (a stale benchmark artifact) turned up only
after running the repo's own test suite.

Core principle: **the deliverable is a verdict backed by reproduction, not by reading the
claim.** A green-suite claim is only true if you ran the suite. A schema-hash claim is only
true if you computed the hash under the real runtime. An artifact is only trustworthy if it
matches the committed generator that produced it.

## 1. Establish the TRUE runtime baseline first (arbitrating review disputes)

A surface/schema/behavior dispute is meaningless until you know which codebase the system
actually runs. A reviewer who diffs against any checkout — even a checked-out repo — can
produce a false blocking finding if that checkout is not the deployed runtime.

- Find the live process and read its real cmdline: `ps -p <pid> -o pid,cmdline`, or
  `ps aux | grep -E "<tool>|<service>"`.
- Resolve symlinks/venvs in the cmdline to the **certified release** path the service runs.
- Diff the relevant source file between the *release* and any *editable checkout*:
  `diff -q <release>/.../schema.py <checkout>/.../schema.py` + `sha256sum` both. If they
  differ, the editable checkout is NOT the runtime baseline — flag any finding built on it.
- Confirm the deployment wiring (which backend/provider the component is set to use) and
  confirm the installed plugin/library version file matches the production baseline.
- Only then compare candidate vs. baseline under that certified release.

## 2. Reproduce claimed SHA-256 digests by brute-forcing the serialization convention

A digest is only verified when you can recompute it. The value depends entirely on the
serialization used to hash the object. When a claimed SHA doesn't match on the first try,
sweep the common conventions deterministically (in one script) — it is a probe, not a guess:

- `json.dumps(obj, sort_keys=True|False, separators=(',',':')|default, ensure_ascii=True|False)`
- with/without a trailing `"\n"`; `repr(obj)`.
- For model-facing tool schemas also try the OpenAI-style wrapper
  `{"type":"function","function":{...}}`, and hashing the base schema vs. the dynamic/merged
  schema (base + plugin overrides applied) separately.
- Try hashing each partially-assembled object (base `COMPUTER_USE_SCHEMA`, the `overrides`
  dict `{"parameters": {...}}`, the merged full schema) — the "raw" and "override" digests
  often hash different objects under different conventions.

If you match the claimed value, note the exact convention in evidence (a byte-for-byte match
against the live runtime is the strongest positive signal). If a convention won't reproduce
(e.g. one of two digests defies every sweep), do NOT call the claim false: verify *content*
equality instead (deep-equal the stored object against the object the runtime produces) and
record the hashing convention as a should-fix documentation gap.

Reference with the working harness: `references/digest-and-surface-reproduction.md`.

## 3. Isolated-runtime surface comparison (plugins / dynamic schemas)

To prove V_n and V_n+1 register an identical model-facing surface:
- Two fresh HERMES_HOME dirs (tempfile), each with only `<home>/plugins/<name>/` copied from
  the installed version vs. the candidate.
- Enable the plugin via a minimal `<home>/config.yaml` `plugins.enabled: [<name>]`. Without
  this, plugin discovery reports `"not enabled in config"` (the `enabled: true` in plugin.yaml
  alone is insufficient).
- Run under the **certified release** venv's python *from the release root* (so the release's
  packages are importable), with `HERMES_HOME` set per side.
- Compare 9+ fields: `registered_backends`, `registered_actions`, `tool_name`, `action_enum`
  (full list), each action's `properties` (byte-equality), the raw schema digest, and the
  override digest. `surfaces_equal` only when the byte-identical call-dict and every compared
  field match. The version string is expected to differ — exclude it from `surfaces_equal`.

## 4. Artifact-vs-generator field-drift check (catch stale evidence)

The flagship benchmark/measurement artifact must have been produced by the *committed*
generator, not an intermediate version. Cheap, high-signal check:
- Grep the artifact for field names (`grep -rn "<field>" .`) that appear **nowhere** in the
  current code → the artifact predates a rename/refactor ("stale-ref hardening" style) and was
  shipped without regeneration.
- Compare the artifact's key set against the keys the generator emits (read the generator's
  dict literal — it will list `input/preserved/lost/mutated/generation_bound/...`).
- Then **run the repo's own test suite** to test any "N passed / green suite" closure claim.
  A committed validation test asserting against the artifact will fail deterministically if the
  artifact is stale. A green-suite claim is only true if `pytest --co` + a full run reproduce it.
- Consequence: a stale flagship artifact + a red suite contradicts a closure gate that requires
  green; this is a real `must_fix` even when the previous model-facing finding was resolved.

## 5. Sanitization / PII verification

- Run the repo's own sanitizer validator (e.g. `assert_sanitized()`) across every sanitized
  artifact, not just one.
- Add an independent regex sweep for IPs, MAC addresses, API-key prefixes (`sk-`, `AKIA`),
  and long base64/hex blobs. Note that legit schema/client hashes (64-char hex) will match a
  generic hex pattern — whitelist the known digest values before calling a hit.

## 6. Distinguish transparent disclosure from hidden failure

A metric that reports "unknown" / "0% reduction" / "not gated / not enforced / not a gate" with
an explicit `reason` and `enforced=false` is a **transparent disclosure**, not necessarily a
defect — the reviewer's job is to confirm the disclosure is honest (no invented backfill,
`generation_status="unknown_no_explicit_generation_field"`, values match the source). Treat
*missing* honesty signals (a metric silently dropped, a gate claimed green that is red) as the
real findings. Report per-item: `passed` / `must_fix` (blocks closure) / `should_fix`
(documentation, reproducibility nit) + `evidence` (file paths and reproduced values).

## 7. Live-artifact regeneration & metric recomputation

Beyond "does this artifact match the committed generator" (§4), verify the artifact is even
the **latest / only** artifact and that its aggregate numbers are derivable from its own parts.

- **Re-stat the file, then re-read it.** Record mtime+size once, do a quick local check, then
  re-read. If mtime/size changed between two reads, a live process (CI, the author, another
  agent) is actively regenerating the evidence — the artifact you first saw may not be the
  current one. Read a second time and only trust the latest. Cross-check the generator
  script's own mtime: an artifact written *after* the generator (newer mtime) should have been
  written *by* that exact generator revision. If the artifact's internal structure matches a
  *different* revision of the generator than the one on disk (compare per-scenario proof keys
  to the generator's dict literals — §4), it is stale/reproduced-by-other-means: flag it.
- **Structural diff beats key presence.** §4 greps for a single field. Stronger: dump the
  generator's per-item proof structure (e.g. scenario `steps`/`proof` dicts) and byte-compare
  against what the generator would emit; a mismatch in key names (`llm_set_native_value` vs
  `llm_select_ref`, `change_action` vs `action`) proves revision drift even when the totals look
  right.
- **Recompute every aggregate from the parts.** Sum per-item counters (per-scenario RPC lists,
  latencies) and compare to the reported totals; they must match exactly. If the report sums
  correctly but the *scenario content* is from an older generator, the aggregate is
  self-consistent but the evidence is stale — that is still a should_fix (pin generator+input
  hash inside the artifact so the gate's input is traceable: `{generator_sha256, input_sha256,
  timestamp}`).
- **Suspect hardcoded constants in the totals block.** A "measurement" that is an assignment
  (`"llm_calls_logical": 3`) rather than a `sum(...)`/`len(...)` over scenario outputs is a
  constant wearing a metric's clothes. It's honest only if the scripted scenarios provably
  produce exactly that many by construction and the code says so; otherwise flag it.
- **Verify restore/un-mutate semantics, not a proxy.** A test that mutates live state
  (writes into a field / window) must snapshot the *exact* prior value and restore that value;
  asserting a derived proxy (`row_count` restored) can pass while the user's actual content was
  clobbered with `""`. Assert the proxy *and* the raw value, and note that a "no mutation"
  claim in a docstring contradicts any write path, even a restored one.
- **A working tree under your feet is a moving target.** If the generator/script files change
  mtime *during* your review (check twice), the authors are iterating live; final findings must
  name the exact artifact+generator hash you actually evaluated, and should note the churn and
  any intermediate failed run (it is honest evidence of flakiness, e.g. a restore that failed
  14/15 then "passed" after a semantics change).

## 8. Visual-render evidence for frontend review

A successful build, a clean console, and DOM assertions do not prove that a frontend composition is acceptable. For a visual release candidate, reproduce the pixels and the interaction state.

- Freeze production after a visual rejection. Treat “unacceptable” or “worse than before” as a rejected baseline, not as permission to add another CSS patch.
- Capture at least desktop `1440×900` and mobile `390×844` at the initial hero, the principal visual section, and the lower-page CTA. Review the actual images; record concrete defects such as duplicate visual roles, sticker/widget feel, crop, accidental full-width borders, dead space, or broken hierarchy.
- For GSAP/IntersectionObserver reveals, do not use an untouched `fullPage` screenshot as sole evidence: below-fold nodes can intentionally remain at `opacity: 0` until the viewport crosses their trigger. Scroll through in viewport-sized steps, wait for each trigger, and capture the important sections in the state a visitor sees. Keep initial-state and post-scroll captures clearly labeled.
- When a composition is rejected, pivot at the architecture level. Remove the rejected markup, state, animation timeline, CSS selectors, and responsive overrides before introducing the new visual role. Assert both the intended count and the absence of legacy elements (for example, one mascot image, zero old stage/journey containers).
- Validate asset geometry before choosing `object-fit` or a crop. Compare the native source ratio to the frame ratio; a mismatch can cut meaningful content without producing a DOM or console error.
- Inspect mobile affordances by pixels and bounds. An underlined text action set to `width: 100%` can become an unintended section divider; use intrinsic width unless a full-width control is intentional.
- Close the loop with two independent gates: automated lint/build/interaction checks, then a local preview and explicit user visual sign-off. Do not deploy public design changes on the strength of technical QA alone.

The reusable probe and checklist are in `references/visual-rejection-recovery.md`.

## Pitfalls

- Comparing against an editable checkout instead of the certified runtime is the classic
  false-poz blocker. Always resolve the live process cmdline first.
- Never re-run aggregated evidence from memory: re-read the file immediately before finalizing
  your report — a concurrently regenerated artifact invalidates findings written against its
  predecessor (an intermediate failed run you may have cited may no longer be on disk).
- The isolated-HERMES_HOME plugin is silently disabled unless `plugins.enabled` is set in that
  home's config — expect the `"not enabled in config"` error and fix the config, not the setup.
- Don't trust "N passed" from a doc; run the suite and quote the reproducible count (e.g. 135
  collected → 134 passed / 1 failed vs. a claimed 133).
- Don't equate an unreproducible digest-string with a false claim: prove content equality, and
  downgrade the exact-convention gap to should_fix.
