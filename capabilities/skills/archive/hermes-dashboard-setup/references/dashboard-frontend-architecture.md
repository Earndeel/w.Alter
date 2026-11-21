# Dashboard Frontend Architecture

## Stack
- React + Vite, monorepo workspace under `web/`
- UI components from `@nous-research/ui` (Card, Badge, Button, Switch, Spinner, Input, ListItem)
- Icons from `lucide-react`
- State: React hooks (useState, useMemo, useCallback, useEffect)
- i18n: `useI18n()` hook with `t.skills.*`, `t.common.*` keys

## Key Files
- `web/src/pages/SkillsPage.tsx` — Skills, Toolsets, and Hub Browser views
- `web/src/lib/api.ts` — API client (`api.getSkills()`, `api.getSkillContent()`, etc.)
- `web/src/App.tsx` — Route mapping (`"/skills": SkillsPage`)
- `hermes_cli/web_server.py` — FastAPI backend serving `/api/*` endpoints
- `hermes_cli/web_dist/` — Built static assets served by `hermes dashboard`

## SkillsPage Structure

Three views toggled by sidebar: `skills` (list), `toolsets` (grid), `hub` (search/install).

Each skill row: Switch (toggle enabled) + clickable name/description → opens side panel.

Side panel (fixed, right, z-50):
- Header: skill name + close button
- Content: `<pre>` monospace for read mode, `<textarea>` for edit mode
- Footer toolbar: Edit / Cancel / Save buttons (always visible at bottom)

## Adding a New Page

1. Create `web/src/pages/YourPage.tsx`
2. Import in `web/src/App.tsx`
3. Add route: `"/your-route": YourPage`
4. Add sidebar link in the layout component

## API Client Pattern

```typescript
// In web/src/lib/api.ts
getSkillContent: (name: string) =>
  fetchJSON<ResponseType>(`/api/skills/${encodeURIComponent(name)}/content`),
saveSkillContent: (name: string, content: string) =>
  fetchJSON<ResponseType>(`/api/skills/${encodeURIComponent(name)}/content`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  }),
```

## Build Pitfalls

- `npm run build` runs `tsc -b && vite build` — `tsc` may be missing from workspace
- Fix: use `../node_modules/.bin/vite build` directly (skips type-checking)
- `vite build` may be detected as long-lived process by `terminal` tool
- Fix: use `execute_code` with `subprocess.run()` instead
- Output goes to `hermes_cli/web_dist/` — dashboard serves from there
- Dashboard must be restarted after build to serve new assets
