# hermes-tui-customization — Restoring the customised TUI design after a Hermes update.

Moved verbatim from SKILL.md on 2026-11-01.

## Post-Update Design Recovery

Hermes updates run `git stash` automatically before pulling new code. If you modified TUI source files (e.g. `branding.tsx`, `banner.ts`, `messageLine.tsx`), they disappear after update because the working tree is reset to upstream.

For a detailed walkthrough of a real recovery session (v0.12.0, 2026-05-06), see `references/post-update-recovery-session-20260506.md`.

For the SSH clipboard fix walkthrough (cmux, tmux, sudo -i, OSC 52 chain), see `references/ssh-clipboard-fix-20260517.md`.

### 1. Find the autostash
```bash
cd ~/.hermes/hermes-agent
git stash list
# Pattern: stash@{N}: On main: hermes-update-autostash-YYYYMMDD-HHMMSS
# stash@{0} is always the most recent (the current update)
```

### 2. Inspect what the stash touched
```bash
# Show only TUI files
git stash show stash@{0} --name-only | grep ui-tui

# Diff a specific file against current HEAD
git diff HEAD stash@{0} -- ui-tui/src/components/branding.tsx
```
### 3. Extract selectively (preferred — avoids conflicts)
Do **not** run `git stash pop` blindly — it can fail on working-tree conflicts or untracked files, and the stash may be incompatible with the new version.

```bash
# Reset TUI to clean post-update state first
git checkout HEAD -- ui-tui/src/

# Extract only the files you want from the stash
git checkout stash@{0} -- ui-tui/src/components/branding.tsx
git checkout stash@{0} -- ui-tui/src/components/appLayout.tsx
git checkout stash@{0} -- ui-tui/src/components/messageLine.tsx
git checkout stash@{0} -- ui-tui/src/components/thinking.tsx
git checkout stash@{0} -- ui-tui/src/components/markdown.tsx
git checkout stash@{0} -- ui-tui/src/domain/details.ts
git checkout stash@{0} -- ui-tui/src/types.ts
git checkout stash@{0} -- ui-tui/src/app/createGatewayEventHandler.ts
git checkout stash@{0} -- ui-tui/src/gatewayTypes.ts
```

**Files commonly customized and worth checking:**
| File | What it controls |
|------|------------------|
| `components/branding.tsx` | `Banner`, `SessionPanel`, `Panel` — startup welcome box |
| `components/appLayout.tsx` | Layout of transcript, composer, overlays — whether `Banner` renders, composer borders |
| `components/messageLine.tsx` | Message bubbles, prefixes, role styling (user-right-align, assistant-left) |
| `domain/details.ts` | `SECTION_DEFAULTS` — whether thinking/tools are expanded/collapsed by default |
| `types.ts` | `SessionInfo`, `RecentSession`, `ActiveTool.emoji` — data contracts |
| `components/thinking.tsx` | Rolling window, emoji headers, sub-accordions, Spinner running prop |
| `components/markdown.tsx` | Link rendering (URL display, useLinkTitle), inline bold, headings |
| `components/markdown.tsx` | Link rendering (raw URLs vs slugified titles), bold/heading styling |
| `createGatewayEventHandler.ts` | Emoji passthrough to recordToolStart |
| `gatewayTypes.ts` | Emoji in tool.start payload type |
| `platform.ts` | `isActionMod`, `isCopyShortcut`, `isRemoteShell` — Cmd+C over SSH fix |
| `openExternalUrl.ts` | Link clicking — OSC 52 clipboard fallback for headless servers |
| `banner.ts` | `CADUCEUS_ART`, `LOGO_ART`, `colorize()` — ASCII art and color gradients |
| `banner.ts` | `CADUCEUS_ART`, `LOGO_ART`, `colorize()` — ASCII art and color gradients |
| `theme.ts` | `DARK_THEME` / `LIGHT_THEME` hardcoded defaults |
| `tui_gateway/server.py` | `_session_info()` — backend data sent to the TUI (recent sessions, etc.) |

**Backend files are NOT in the stash** — if you added `recent_sessions` or other backend-side data to `_session_info()`, those changes live in `tui_gateway/server.py` which is NOT captured by `git stash` (it's in the repo but the stash only captures the *pre-update* working tree). You must re-apply backend patches separately. The restore script handles this automatically — see `templates/restore-tui-design.sh`.

### 4. Verify compatibility immediately
```bash
cd ~/.hermes/hermes-agent/ui-tui
npm run build
```

**If the build fails with type errors** (e.g. `Property 'X' does not exist on type 'Y'`, `Module has no exported member`), the stash is **incompatible** — the TUI internals changed between versions. In that case:
1. Reset the file(s): `git checkout HEAD -- ui-tui/src/`
2. Re-read the current source
3. Re-apply your design changes manually against the new API

**If the build fails with "No matching export in ... for import ...":** This means upstream **removed or renamed** an export that your override files still reference. The restore script blindly copies override files into the repo without checking compatibility. This is the #1 cause of broken restores after updates.

**Diagnosis + fix workflow:**
1. Read the error: `No matching export in "src/config/X.ts" for import "SYMBOL_NAME"` tells you exactly which symbol died
2. Find the upstream commit: `git log --all --oneline --diff-filter=M -- ui-tui/src/config/X.ts | head -5` then `git show <commit> -- ui-tui/src/config/X.ts` to see what changed
3. If the commit is a merge, check the PR message: `git show <commit>` — the PR description often explains the rationale (e.g. "no history truncation" = `FULL_RENDER_TAIL_ITEMS` removed because all messages now render full text)
4. Update the override files in `~/.hermes/tui-overrides/` (NOT the repo copies — those get overwritten each restore):
   - Remove the dead import
   - Update the usage to match the new API (e.g. `boundedHistoryRenderText(msg.text)` → `msg.text` when truncation is removed)
   - Remove any props that referenced the dead symbol from component interfaces
5. Re-run the restore script to copy + rebuild

**Pitfall:** The restore script's `npm run build` will report errors but the script itself exits 0 (because `npm run build` pipes through `tail -5` which swallows the exit code). Always check the build output visually — "Done" at the end does NOT mean the build succeeded.

For a concrete example (v0.14.0, 2026-05-21: `FULL_RENDER_TAIL_ITEMS` and `boundedHistoryRenderText` removed by PR #28829), see `references/override-compat-fix-20260521.md`.

### 5. What survives vs what doesn't

| Survives update? | Location | Why |
|------------------|----------|-----|
| ✅ Yes | `~/.hermes/skins/<name>.yaml` | Outside the git repo |
| ✅ Yes | `~/.hermes/config.yaml` `display:` section | Outside the git repo |
| ❌ No | `ui-tui/src/**/*.tsx` `ui-tui/src/**/*.ts` | Inside repo, reset on update |
| ❌ No | `cli.py`, `banner.py`, etc. | Inside repo, reset on update |
| ✅ Yes | `/etc/sudoers.d/keep-ssh-env` | Outside the repo — preserves SSH_CONNECTION through sudo |
| ✅ Yes | `/home/ubuntu/.tmux.conf` | Outside the repo — tmux config for ubuntu user |

### 6. Permanent workaround: backup dir + restoration script
For designs that require source modifications, maintain copies outside the repo and a rebuild script:

```bash
# 1. Create backup directory
mkdir -p ~/.hermes/tui-overrides

# 2. After each design change, snapshot the files
cp ui-tui/src/components/branding.tsx ~/.hermes/tui-overrides/
cp ui-tui/src/components/appLayout.tsx ~/.hermes/tui-overrides/
cp ui-tui/src/components/messageLine.tsx ~/.hermes/tui-overrides/
cp ui-tui/src/components/thinking.tsx ~/.hermes/tui-overrides/
cp ui-tui/src/components/markdown.tsx ~/.hermes/tui-overrides/
cp ui-tui/src/components/markdown.tsx ~/.hermes/tui-overrides/
cp ui-tui/src/domain/details.ts ~/.hermes/tui-overrides/
cp ui-tui/src/types.ts ~/.hermes/tui-overrides/
cp ui-tui/src/app/createGatewayEventHandler.ts ~/.hermes/tui-overrides/
cp ui-tui/src/gatewayTypes.ts ~/.hermes/tui-overrides/

# 3. Create restoration script at ~/.hermes/scripts/restore-tui-design.sh
#    (see templates/restore-tui-design.sh in this skill for a ready-to-use script)
```
```

**Usage after future updates:**
```bash
hermes update && bash ~/.hermes/scripts/restore-tui-design.sh
```

**Belt-and-suspenders guard (recommended):** add `/root/.hermes/scripts/ensure-tui-design.sh` and call it from `/root/bin/start-hermes-root-new` before launching `hermes --tui`. The guard compares `~/.hermes/tui-overrides/*` against the live repo files; if an update reset them, it runs `restore-tui-design.sh` automatically. This covers updates launched outside the `.bashrc` `hermes()` wrapper (for example from inside a TUI or a non-interactive shell).

Also set `set -euo pipefail` in `restore-tui-design.sh`; otherwise `npm run build 2>&1 | tail -5` can mask a failed build because `tail` exits 0. Tiny shell foot-gun, naturally.

This is more reliable than stash recovery because:
- It doesn't depend on the stash still existing (stashes can be dropped)
- It handles API changes gracefully — if a file no longer exists, the `cp` fails early and you know manual porting is needed
- It rebuilds automatically, so you verify immediately
- It re-applies backend patches (`server.py`) which are NOT captured by git stash

See also `templates/restore-tui-design.sh` in this skill for a ready-to-use script.
See also `references/cmux-multi-instance-launcher.md` for the macOS cmux → VPS multi-instance TUI launcher pattern.

