---
name: hermes-version-check
description: >
  Before answering questions about Hermes Agent versions, updates, or features —
  ALWAYS check the actual installed version first. Never assume from documentation alone.
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [hermes, version, update]
---

# Hermes Version Check

## When to Use

Before ANY discussion about Hermes Agent version, updates, features, or changelog.

## Steps

1. Check installed version AND human-readable release name:
```bash
cd ~/.hermes/hermes-agent && git describe --tags --abbrev=0
# v2026.5.29 → this is v0.15.1. The v0.X.Y names live in commit messages.
# Find the release name:
git log --oneline --all | grep -iE "bump version|release v" | head -5
```

2. Check if HEAD is ahead of the latest tag (common — main has post-release commits):
```bash
LATEST_TAG=$(git tag -l 'v*' --sort=-v:refname | head -1)
echo "Latest tag: $LATEST_TAG"
echo "HEAD is $(git rev-list ${LATEST_TAG}..HEAD --count) commits ahead"
git log --oneline ${LATEST_TAG}..HEAD
```

3. List what changed in the current release vs the previous one:
```bash
PREV_TAG=$(git tag -l 'v*' --sort=-v:refname | sed -n '2p')
CURR_TAG=$(git tag -l 'v*' --sort=-v:refname | sed -n '1p')
git log --oneline ${PREV_TAG}..${CURR_TAG}
```

4. Check if update available:
```bash
cd ~/.hermes/hermes-agent && git fetch origin --tags 2>/dev/null
git describe --tags --abbrev=0 origin/main
```

5. ONLY THEN reference skill docs or release notes.

## Pitfalls

- Skill reference files (e.g., `references/v014-features.md`) may be OUTDATED relative to the actual codebase version. The code is updated by `hermes update` but skill docs lag behind.
- Never say "we're on version X" without running `git describe --tags --abbrev=0` first.
- `hermes --version` may show a compiled version that differs from git tags — always use git.
- **Git tags use date format** (`v2026.5.29`), NOT the human-readable release name (`v0.15.1`). The release name only appears in commit messages (`chore: release v0.15.1`). Always resolve the human name before telling the user which version they're on.
- **HEAD is usually ahead of the latest tag.** `git describe --tags` returns the tag, but there are often post-release fix commits on main. Always check `${LATEST_TAG}..HEAD` to report the full picture.
- When the user asks "what's the last update" or "qu'est-ce qui a changé", they want the **new features**, not just the version number. Run `git log --oneline ${PREV_TAG}..${CURR_TAG}` to get the changelog, then look for `feat:` commits. If there's a dedicated release PR or changelog file, read it.
- When the user asks about a specific new feature (e.g., "c'est quoi tool search"), find the implementation files and the introducing commit (`git log --all --oneline -- <file>`), not just the commit message.
- **"La dernière mise à jour" ≠ `hermes update`.** The user may mean a cron job that just ran, a session that just completed, or a background task — not necessarily a CLI version upgrade. Always ask for clarification or check recent session history before assuming they mean a version bump. If they say "tu viens de passer en X" or "la dernière update que tu viens d'exécuter", they may be referring to something the agent did in a recent background/cron session, not `hermes update`.
- **"C'est quoi X ?" about a feature = find the implementation, not just the docs.** When the user asks about a specific feature (e.g., "c'est quoi tool search"), find the actual source files (`tools/tool_search.py`), the introducing commit (`git log --all --oneline -- tools/tool_search.py`), and trace the logic. Don't just read the skill reference files which may be stale.
- **"Vérifie que ça fonctionne / compare avant-après" = real measurements + tests.** When the user asks you to verify a config change works, don't just explain the theory. Run actual measurements (token counts, schema sizes), run the test suite (`pytest tests/tools/test_tool_search.py`), and present a concrete before/after table. The user trusts numbers, not explanations.
- **Tag format: `v2026.M.D` not `v0.X.Y`.** Hermes uses CalVer for git tags (`v2026.5.29`) but SemVer in release commit messages (`v0.15.1`). To find the SemVer: `git log --oneline --all | grep -i "bump version\|release v"`. The mapping is: v2026.5.28 = v0.15.0, v2026.5.29 = v0.15.1, v2026.5.29.2 = v0.15.2.

## Verification

```bash
# Installed vs latest
LOCAL=$(cd ~/.hermes/hermes-agent && git describe --tags --abbrev=0 2>/dev/null)
REMOTE=$(cd ~/.hermes/hermes-agent && git fetch origin --tags 2>/dev/null && git describe --tags --abbrev=0 origin/main 2>/dev/null)
echo "Local: $LOCAL | Remote: $REMOTE"
```
