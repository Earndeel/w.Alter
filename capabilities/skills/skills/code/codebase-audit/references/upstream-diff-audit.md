# Upstream-Diff Audit (fork update / merge planning)

Use when the ask is: "audit our local changes before a Hermes (or any fork)
update" — compare the local worktree against `origin/main` to plan how
uncommitted/divergent work will survive a rebase/merge, classify conflict
risk per file, and verify the upstream extension surfaces before writing new
plumbing. Read-only; no merge/rebase/stash/clean.

## The two-axis separation (do this FIRST, it reframes everything)

When local HEAD is N commits behind origin/main, a naive `git diff origin/main
-- <file>` mixes TWO independent changes into one blob:

1. **Upstream drift** — what upstream changed *since your fork point*.
   `git diff HEAD <base> -- <files>`
2. **Local worktree changes** (the actual feature under review) —
   `git diff -- <files>` (HEAD vs working tree).

Always compute both and read them separately:

```bash
BASE=$(git rev-parse origin/main)          # or the exact target commit
git diff --stat $BASE -- path/a.py path/b.py   # upstream drift
git diff --stat --       path/a.py path/b.py   # local feature edits
git diff --stat $BASE -- $(git ls-files)       # whole-repo drift size
```

Key insight: **the merge target is origin/main, NOT local HEAD.** Since local
HEAD is behind, upstream may have rebuilt files wholesale. So "local feature
vs upstream" is what matters, and local-vs-HEAD only tells you how big your
own feature is. Don't let the two get conflated.

## Classify conflict risk per file: A/B/C/D

- **A — Clean.** Local edits land in regions upstream never touched (no
  upstream drift in the file, or fully disjoint hunk locations). Carry-over
  is safe. E.g. a brand-new classifier file where the 40-line upstream
  original is untouched.
- **B — Low.** Local edits are in upstream-modified files but hunk locations
  don't collide (mechanical merge). Typically: feature added inside a config
  dict / function zone between two upstream hunks.
- **C — Overlap.** Both sides edit the *same large function* (e.g. both add a
  branch inside `execute_tool_calls_sequential`) or interleaved zones of the
  same file. Mechanical but must be merged hand-in-hand.
- **D — Forked wholesale / rebase required.** Upstream massively rebuilt the
  file (e.g. +3157/-167 on `plugins.py`) while local touched it too. You must
  re-base the local change onto the NEW upstream shape, not apply it to local
  HEAD. Highest risk.

Hunk-level collision check — put both hunks side by side:

```bash
git diff HEAD $BASE -- agent/tool_executor.py | grep -nE '^@@'   # upstream hunks
git diff --            agent/tool_executor.py | grep -nE '^@@'   # local hunks
```

If the `@@ -line,count` ranges don't intersect, overlap is low even in the
same file. Report the exact local line ranges (core lines) and which upstream
drift hunks they sit between/next to.

## Verify the upstream extension mechanism BEFORE writing new plumbing

For an audit whose feature adds a *new backend/decoration hook* (plugins.py,
registry-files), the single most valuable question is: **does upstream already
provide a generic seam for this?** Grepping the upstream `Plugins/PluginContext`
for the feature name often returns empty — that is the finding, not the absence
of a need.

Worked example (Hermes):
- Local feature added a typed `PluginContext.register_computer_use_backend` +
  a module-global `_BACKEND_FACTORIES` dict in `tools/computer_use/backend.py`.
- Upstream `register_tool` returns a **`PluginRegistration`** disposal handle
  via `_track_replacement` + `snapshot_registration`/`restore_registration`
  (tool registry lives host-side in `tools/registry.py`; `override=True` is
  trust-gated via `allow_tool_override`).
- Upstream exposes **typed** provider registries (`register_browser_provider`,
  `register_web_search_provider`, ...) each storing into an edge-side registry
  selected by provider name — but **no generic capability-keyed backend
  registry**, and **no hook that lets a tool result declare *terminality*
  (close the tool phase / freeze tools)**. `transform_tool_result`/`post_tool_call`
  hooks can rewrite/observe a result but cannot tell the loop to stop.

Conclusion you'd state: the minimal *generic* seam missing upstream is (a) a
capability-keyed backend-provider registry on PluginContext returning a
`PluginRegistration` rollback handle (the `register_tool` pattern generalized),
and (b) a terminality-decision hook. Until that exists, a typed method +
module-global dict is *not* monkey-patching (V1-safe) but IS tool-specific —
flag that it should be folded into the upstream generic pattern, not kept as a
parallel registry.

## Pitfalls

1. **Diffing against local HEAD when the merge target is origin/main.** Local
   HEAD is behind; `git diff HEAD` hides upstream's wholesale rebuild of the
   file you touched. Always diff against the target base commit.
2. **A huge `plugins.py`-style drift signals D-grade, not just big.** When
   upstream went +3k/-1xx, your local +21-line method must be re-based onto
   the new class shape; the two PluginContexts are different objects.
3. **Line counts expose file provenance fast.** `wc -l` local vs upstream on
   a "new" file (e.g. local 227 vs upstream 40) tells you it's mostly your
   feature. Use `git cat-file -e HEAD:path` + `git ls-files path` to check
   whether a file is tracked/new at HEAD.
4. **Same-named test files may be identical upstream/local** while your local
   edit only touches one — always `git diff HEAD $BASE` per test file, and
   check `ls` for feature-specific test files upstream lacks (those are clean
   A-grade additions).

## Deliverable shape

Per-file table: file | local feature change (+/-) | upstream drift (+/-) |
class | collision note (hunk ranges). Then a short verdict: which files are
clean, which need manual merge (C), which must be re-based (D), and the
specific missing generic seam (with the upstream mechanism it should ride on).
Keep the V1-freeze / behavior-frozen note explicit when the feature is an
additive, opt-in default.
