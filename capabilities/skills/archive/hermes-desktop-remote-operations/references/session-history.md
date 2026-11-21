# Desktop session-history display

Use this reference when the Home screen appears to show only a few conversations.

## Decision flow

1. Confirm the user is looking at the Home/project overview, not the complete session list or session search.
2. In the sidebar display/filter menu, check that the grouping is **Project**.
3. With Project grouping active, enable **Show all sessions**. The option is conditional on project grouping in the current renderer; it is not a global server retention setting.
4. Re-open the project/Home row and verify that older loaded sessions are rendered.
5. If sessions are still absent, check the Desktop build, active Hermes profile, backend/gateway identity, and search/session-list pagination separately.

## Current renderer clues

The current Desktop source uses:

- `PROJECT_PREVIEW_COUNT = 3` for the collapsed project overview preview.
- `sidebarShowAllSessions` as a persisted UI preference under the local-storage key `hermes.desktop.sidebarShowAllSessions`.
- `showAllSessions ? Infinity : PROJECT_PREVIEW_COUNT` when choosing how many already-loaded project sessions to render.
- `SIDEBAR_SESSIONS_PAGE_SIZE = 50` for the ordinary sidebar load window, with a larger filtered window in the current source.

These are implementation clues, not promises that every compiled Mac build has the same constants. Do not advise editing a server checkout to change a compiled Electron renderer; first verify the installed Desktop build and use the exposed UI control. Do not infer deletion from a three-row preview; confirm through the full list or search.
