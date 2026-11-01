---
name: petdex
description: Install and select animated petdex mascots for Hermes.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [petdex, mascot, display, cli, tui, desktop]
    category: productivity
    homepage: https://petdex.dev
---

# Petdex Skill

Browse, install, and select animated "pet" mascots from the public
[petdex](https://github.com/crafter-station/petdex) gallery. An installed pet
reacts to agent activity (idle, running a tool, reviewing, error, done) across
the Hermes CLI, TUI, and desktop app. This skill drives the `hermes pets` CLI
and the `display.pet` config — it does not generate sprites.

## When to Use

- The user wants a desktop/terminal mascot or asks about "pets" / petdex.
- The user wants to change, preview, or disable the active pet.
- Diagnosing why a pet isn't showing (terminal graphics support, config).

## Prerequisites

- Network access to `petdex.dev` for the gallery/manifest (read-only, no auth).
- Pillow (a core Hermes dependency) for sprite decoding — already installed.
- For full-fidelity terminal rendering: a graphics-capable terminal (kitty,
  Ghostty, WezTerm, iTerm2, or sixel). Otherwise a truecolor Unicode
  half-block fallback is used automatically.

## How to Run

Use the `terminal` tool to run `hermes pets <subcommand>`.

## Quick Reference

| Goal | Command |
| --- | --- |
| Browse the gallery | `hermes pets list` (add a substring to filter: `hermes pets list cat`) |
| List installed pets | `hermes pets list --installed` |
| Install a pet | `hermes pets install <slug>` (add `--select` to make it active) |
| Set the active pet | `hermes pets select <slug>` (omit slug for a picker) |
| Resize the pet everywhere | `hermes pets scale <factor>` (e.g. `0.5`, clamped 0.1–3.0) |
| Preview/animate in terminal | `hermes pets show [slug] [--cycle] [--state run]` |
| Disable the pet | `hermes pets off` |
| Remove a pet | `hermes pets remove <slug>` |
| Diagnose setup | `hermes pets doctor` |

## Procedure

1. Find a pet: `hermes pets list <query>` and note its `slug`.
2. Install + activate: `hermes pets install <slug> --select`.
3. Preview it: `hermes pets show` (Ctrl+C to stop).
4. Confirm setup: `hermes pets doctor` — shows the resolved pet, configured
   render mode, detected terminal graphics protocol, and effective mode.

Pets install into `<HERMES_HOME>/pets/<slug>/` (profile-aware). Selecting a pet
writes `display.pet.slug` + `display.pet.enabled` to `config.yaml`.

## Configuration

Under `display.pet` in `config.yaml`:

- `enabled` (bool) — master on/off.
- `slug` (str) — active pet; empty = first installed.
- `render_mode` — `auto` (detect) | `kitty` | `iterm` | `sixel` | `unicode` | `off`.
- `scale` (float) — on-screen size of the native 192×208 frames (default 0.33,
  clamped 0.1–3.0). One knob resizes every surface; set it with
  `hermes pets scale <factor>`, the `/pet scale` slash command, or the desktop
  Appearance slider.
- `unicode_cols` (int) — width in columns for the Unicode fallback.

## TUI Integration

### Approach A: PetPane (above composer, right-aligned)

The pet renders in the TUI via the `PetPane` component in `ui-tui/src/components/appLayout.tsx`:

```tsx
const PetPane = memo(function PetPane({ busy }: { busy: boolean }) {
  const { enabled, grid, kitty } = usePet()
  if (!enabled || busy || (!grid && !kitty)) return null
  return (
    <NoSelect flexShrink={0} justifyContent="flex-end" paddingX={1} width="100%">
      {kitty ? <PetKitty color={kitty.color} placeholder={kitty.placeholder} /> : null}
      {!kitty && grid ? <PetSprite grid={grid} /> : null}
    </NoSelect>
  )
})
```

**Default position:** right-aligned, above the composer input. The `busy` prop hides it when the agent is active (status bar spinner takes over).

**To change position:** modify `justifyContent` in the `NoSelect` wrapper:
- `"flex-end"` → right-aligned (default)
- `"flex-start"` → left-aligned
- `"center"` → centered

### Approach B: PetTicker (inline status bar, replaces spinner)

For users who want the pet to **replace the status bar spinner** (kaomoji/emoji/unicode) with pet animations:

1. Add a `PetTicker` component in `ui-tui/src/components/appChrome.tsx` that renders the pet sprite inline (single row).
2. In `StatusRule`, call `usePet()` and conditionally render `PetTicker` instead of `FaceTicker` when `pet.enabled` is true.
3. Pass `state` to `PetTicker` based on `busy` (maps to `'run'` or `'idle'`).

```tsx
// In StatusRule (appChrome.tsx):
const pet = usePet()
const petState = busy ? 'run' : 'idle'

// Replace the FaceTicker rendering:
{pet.enabled ? (
  <PetTicker pet={pet} state={petState} startedAt={turnStartedAt} t={t} />
) : busy ? (
  <FaceTicker color={statusColor} startedAt={turnStartedAt} style={indicatorStyle} />
) : showNotice ? null : (
  <Text color={statusColor}>{status}</Text>
)}
```

**PetTicker** renders:
- **Kitty mode:** first row of the placeholder grid with pet color (out-of-band image transmission)
- **Unicode mode:** first row of the sprite grid as truecolor half-blocks
- **Fallback:** state icon (● idle, ⚡ run, ◐ review, ✕ failed, 👋 wave, ▲ jump, ◌ waiting)

**Source locations:**
- TUI source: `/root/.hermes/hermes-agent/ui-tui/src/`
- Pet hook: `src/app/usePet.ts` (fetches frames via `pet.cells` RPC)
- Sprite renderer: `src/components/petSprite.tsx` (PetSprite + PetKitty)
- Pet picker overlay: `src/components/petPicker.tsx`
- Gateway RPCs: `tui_gateway/server.py`

## Pitfalls

- **TUI rebuild required after code changes.** After modifying `appLayout.tsx` or any pet component, rebuild with `cd /root/.hermes/hermes-agent/ui-tui && npm run build`. The bundle is at `dist/entry.js`.
- **Monorepo requires `npm ci`.** If build fails with unresolved dependencies (`ink-text-input`, `chalk`, etc.), run `npm ci` from the repo root first — `npm install` alone may not hoist packages correctly.
- **Local modifications can remove features.** If a pet feature appears missing (e.g. PetPane not in appLayout.tsx), check `git diff HEAD -- <file>` before assuming it's upstream. Restore with `git checkout HEAD -- <file>`.
- **Approach A and B are complementary, not mutually exclusive.** PetPane (full sprite above composer) and PetTicker (mini-indicator in status bar) can coexist. A common bug: implementing PetTicker and deleting PetPane from appLayout.tsx leaves only a 1-row stub — the user sees "one line of pixels" instead of the full mascot. Always keep PetPane in the layout; PetTicker is an addition, not a replacement for it.
- **Diagnostic shortcut for "pet shows only one line":** check `git diff HEAD -- ui-tui/src/components/appLayout.tsx` for a missing `PetPane` component. If absent, restore it (import `usePet`, `PetKitty`, `PetSprite`, add the `PetPane` memo, and render `<PetPane />` above `<PerfPane id="prompt">` in the `!overlay.agents` block).
- A pet only shows once one is installed AND selected (`enabled: true`).
- Inside a pipe/redirect (no TTY) terminal rendering is disabled by design.
- The petdex npm CLI installs to `~/.codex/pets`; Hermes uses its own
  profile-scoped `<HERMES_HOME>/pets/` instead — install through `hermes pets`.
- **Gallery is massive (3 000+ pets).** Never run `hermes pets list` without a filter — it returns only the first ~40 lines. Always use `hermes pets list <query>` with a keyword matching the user's intent (e.g. `cat`, `robot`, `maid`, `owl`). If the first keyword yields 0 results, try 2-3 synonyms before concluding the category doesn't exist.
- **No "butler" category exists.** The closest thematic matches are `maid` (6 results) or `robot` (5 results). Don't burn cycles searching for roles that aren't in the gallery.

## Verification

- `hermes pets doctor` reports `✓ ready` when a pet is installed, selected,
  enabled, and Pillow is importable.
