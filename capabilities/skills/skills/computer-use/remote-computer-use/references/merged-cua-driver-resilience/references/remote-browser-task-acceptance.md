# Remote browser task acceptance

## Sanitized evidence pattern

A reliable native Mac browser task has four separately verified stages:

1. **Intent** — the user names the browser; that browser is authoritative. Do not
   substitute a remembered browser preference.
2. **Launch/navigation** — use the deterministic remote launch/URL route when the
   transport is healthy. Verify the requested browser has a substantive live
   window; `process_running=true` alone is not completion.
3. **Page state** — capture fresh AX/page state after navigation. For a request
   to select “the first video,” require a real video card, video link, or
   equivalent labelled target.
4. **Mutation/read-back** — act only from the current snapshot, then capture
   again. `unverifiable` means inspect first, not repeat blindly.

## Empty-state rule

A page title such as `YouTube` does not prove that a video feed loaded. If the
page exposes only an empty-state message such as `Try searching to get started`
and no video cards/links, there is no selectable “first video.” Stop and report
the exact blocker. Do not click Home, Search, or another unrelated control just
to produce an apparently successful transition.

## Pixel/AX split

If screenshot pixels are invalid while AX is coherent, labelled semantic
controls may still be used when they are explicit and reversible. That does
not establish visual identity of content. Never claim that a video was
selected based only on a toolbar, tab title, page title, or a successful click
on a reload/navigation control.

## Scope boundary

This reference is for explicit native-browser actions on the user's Mac. Public
web research and extraction remain on the web front door/headless route; do not
use the user's visible browser for unrelated scraping.
