# Independent review of a frozen artifact (tarball / release bundle / delegated subagent audit)

Use when the source is NOT a live git tree but a **frozen artifact**: a `.tar.gz`
release bundle, a "lot" / iteration deliverable, or anything where results are
pre-stated by the parent ("51/51 tests, 8/8 contract, live_execution_performed=false").
**Never trust or replay those claims — reproduce them yourself in an isolated copy.**
The whole point of an independent reviewer is verifying, not echoing a summary.

## Verification ladder (do all, in order)

1. **Verify the archive hash before touching anything.**
   `sha256sum <archive>` against the stated expected SHA-256. Re-hash at the end
   too — prove you left the deliverable unmodified.

2. **Extract ONLY into your own temp space.** Never edit the archive or any
   source file. Keep the copy outside the deliverable path (e.g. `/root/tmp_xxx/`).

3. **Verify the bundle's inner `SHA256SUMS`** with `sha256sum -c`. Then reconcile
   both directions: every SHA256SUMS entry should exist on disk, and every shipped
   file should be in SHA256SUMS.
   - Trap: artifacts created by YOUR test runs (`.pytest_cache/`, `__pycache__/`)
     are yours, not the archive's. Before flagging a "missing from SHA256SUMS"
     file, confirm it's absent from a fresh `tar tzf <archive>` listing — if it's
     not in the tar, it's your byproduct, not a defect.

4. **Run the project's canonical commands in the extracted copy** — exactly as the
   README/docs prescribe (tests, benchmark, lint), never from the parent's numbers
   or the archive itself. Capture true pass/fail and exit codes.

5. **Determinism / anti-fabrication check (the key step).** For any committed
   result artifacts the bundle claims to reproduce (benchmark reports, event
   traces, screenshots of output), REGENERATE them from the code in a fresh dir
   and byte-compare with what's shipped:
   - events/traces (JSONL): compare line-by-line as parsed JSON objects
   - reports/summaries (JSON): compare semantically (json.dumps sort_keys)
   - **Identical events + metrics ⇒ the committed results are genuinely
     reproducible from code — honest, not fabricated post-hoc.**
   - Benign diffs to ignore: absolute `trace_path`/output-directory strings
     (location, not content); wall-clock timestamps.
   - A committed artifact you CANNOT reproduce — or that ships `success=true`
     from a path that can only ever produce it — is a red flag for fabrication.

6. **Static guard greps** — verify the claims you care about directly; do NOT rely
   on an in-repo test asserting them (tests can be written to pass by construction):
   - forbidden app markers / recipe terms: `grep -rniE 'finder|spotify|...` in runtime
   - forbidden imports (web/browser/RPA engines): parse imports or
     `grep -rn '^import|^from'`
   - hidden loops / polling / retry / sleep: `grep -rniE 'time.sleep|while True|retry|poll'`

7. **"By-construction" success detection.** Watch for a simulation harness that
   synthesizes result events from the scenario's OWN expected values (route,
   `postcondition.satisfied=true`, expected call counts). Such a run always passes
   — it validates the pipeline/schema, NOT behavior. Confirm the output honest-ly
   marks this (`live_execution_performed=false`, `evidence_class="contract_only"`,
   `mode=contract`). Suggest a `synthetic: true` flag in the report if it would
   make the nature unmistakable to a lazy reader.

## Reporting

- Separate **must-fix** (file + reason + exact fix) from **non-blocking
  suggestions**. "No must-fix" IS a valid, correct outcome when the artifact is
  genuinely sound — do not manufacture issues to appear thorough.
- A "documented conceptual output that differs from the code" is not a defect if
  the docs explicitly label that payload as *conceptual* / illustrative.
- State explicitly at the end: files created/modified (should be none, or only
  your scratch copies) and that the source hash is unchanged (step 1).
