# hermes-tui-customization — Link rendering (raw/full URLs), markdown styling, clicking links on headless servers.

Moved verbatim from SKILL.md on 2026-11-01.

## Link Rendering — Show Raw URLs (components/markdown.tsx)

By default, the TUI renders links as underlined text with a slugified title (via `urlSlugTitleLabel` or `useLinkTitle` page-title fetch). The user sees underlined text like "Docs" but not the actual URL. This is frustrating when trying to copy or verify links.

**Fix:** In `markdown.tsx`, change `defaultLinkLabel` to return the raw URL, and disable `useLinkTitle` fetching:

```tsx
// Before: slugified title
const defaultLinkLabel = (url: string) =>
  url.startsWith('mailto:') ? url.replace(/^mailto:/, '') : /^https?:\/\//i.test(url) ? urlSlugTitleLabel(url) : url

// After: raw URL
const defaultLinkLabel = (url: string) =>
  url.startsWith('mailto:') ? url.replace(/^mailto:/, '') : url
```

In `ResolvedLink`, remove the `useLinkTitle` hook:

```tsx
// Before
function ResolvedLink({ fallbackLabel, t, url }: ResolvedLinkProps) {
  const fetched = useLinkTitle(url)
  const display = fetched || fallbackLabel || defaultLinkLabel(url)
  // ...

// After
function ResolvedLink({ fallbackLabel, t, url }: ResolvedLinkProps) {
  const display = fallbackLabel || defaultLinkLabel(url)
  // ...
```

Clean up unused imports: remove `urlSlugTitleLabel` and `useLinkTitle` from the `externalLink.js` import.

**Behavior after fix:**
- Bare URLs (`https://example.com/path`) → full URL shown, underlined, accent color
- Markdown links (`[click here](https://...)`) → "click here" shown (the link text is the `fallbackLabel`)
- Autolinks (`<https://...>`) → full URL shown

**Pitfall:** `useLinkTitle` fetches page titles via HTTP HEAD requests in the background. Removing it eliminates network calls for every link in the response — a minor performance win.

## Markdown Styling (components/markdown.tsx)

Inline bold (`**text**`) and headings (`# title`) can be styled for more contrast:

**Bold inline** (line ~158, MdInline function): change from bare `bold` to `bold` + color:
```tsx
// Before: <Text bold key={...}>
// After:  <Text bold color={t.color.gold} key={...}>
```

**Headings** (line ~387, HEADING_RE match + SETEXT_RE): add underline for extra distinction:
```tsx
// Before: <Text bold color={t.color.amber} key={...}>
// After:  <Text bold color={t.color.gold} underline key={...}>
```

Using `t.color.gold` (#FFD700) vs `t.color.cornsilk` (#D0FBFE body text) creates visible contrast on dark terminals. `amber` works too but `gold` is brighter.

## Link Rendering (components/markdown.tsx)

By default, the TUI renders markdown links as underlined text with a slugified title (e.g. `urlSlugTitleLabel` turns `https://example.com/path/to/docs` into "Docs"). Users who want to see the full URL should:

1. In `defaultLinkLabel`, remove the `urlSlugTitleLabel` call — just return the raw URL
2. In `ResolvedLink`, remove `useLinkTitle` — don't fetch page titles
3. Remove unused imports (`urlSlugTitleLabel`, `useLinkTitle`)

After: bare URLs show the full URL underlined, markdown links `[text](url)` still show the link text.

## Link clicking on headless servers

When the user clicks a link in the TUI, `openExternalUrl()` tries to run `xdg-open` (Linux) or `open` (macOS). On a headless VPS, `xdg-open` is typically not installed, and even if it were, the browser would open on the server, not the user's machine.

### Fix

In `lib/openExternalUrl.ts`, when no browser opener is available (or it fails), copy the URL to clipboard via OSC 52:

```typescript
function copyUrlToClipboard(url: string, dependencies: OpenDependencies = {}): boolean {
  const spawnFn = dependencies.spawn ?? spawn

  // Best-effort native clipboard write (silently fails without DISPLAY)
  try {
    const child = spawnFn('xclip', ['-selection', 'clipboard', '-in'], {
      stdio: ['pipe', 'ignore', 'ignore']
    })
    child.stdin?.end(url)
    child.once('error', () => {})
    child.unref()
  } catch {}

  // OSC 52 — travels over SSH to the local terminal
  const b64 = Buffer.from(url, 'utf8').toString('base64')
  process.stdout.write(`\x1b]52;c;${b64}\x07`)

  return true
}
```

Wired into `openExternalUrl`:
- `if (!command)` → calls `copyUrlToClipboard()` instead of returning false
- `child.once('error', ...)` → calls `copyUrlToClipboard()` as fallback when xdg-open fails

## Link Rendering: Show Raw URLs

By default, the TUI's markdown renderer transforms URLs into friendly labels:
- `urlSlugTitleLabel(url)` extracts a title-like slug from the path (e.g. `https://example.com/docs` → "Docs")
- `useLinkTitle(url)` fetches the page's `<title>` tag and shows that instead

**User preference: show the raw URL.** When the user can't see the full URL, they can't verify where a link goes or copy it.

### Fix in `components/markdown.tsx`

1. **`defaultLinkLabel`** — return the URL as-is, don't slugify:
```tsx
// Before:
const defaultLinkLabel = (url: string) =>
  url.startsWith('mailto:') ? url.replace(/^mailto:/, '') : /^https?:\/\//i.test(url) ? urlSlugTitleLabel(url) : url

// After:
const defaultLinkLabel = (url: string) =>
  url.startsWith('mailto:') ? url.replace(/^mailto:/, '') : url
```

2. **`ResolvedLink`** — remove `useLinkTitle` hook entirely:
```tsx
// Before:
function ResolvedLink({ fallbackLabel, t, url }: ResolvedLinkProps) {
  const fetched = useLinkTitle(url)
  const display = fetched || fallbackLabel || defaultLinkLabel(url)
  // ...
}

// After:
function ResolvedLink({ fallbackLabel, t, url }: ResolvedLinkProps) {
  const display = fallbackLabel || defaultLinkLabel(url)
  // ...
}
```

3. **Clean imports** — remove `urlSlugTitleLabel` and `useLinkTitle` from the import line.

**Result:** `[click here](https://example.com/path)` shows "click here" (underlined). Bare `https://example.com/path` shows the full URL (underlined). No more hidden URLs.

**Pitfall:** If you keep `useLinkTitle`, it fetches page titles over the network and replaces URLs with titles like "Hermes Agent Documentation" — the user can't see where the link goes.

## Link Rendering: Show Full URLs

By default, the TUI transforms URLs into short labels via `urlSlugTitleLabel()` (extracts a title from the URL path) and `useLinkTitle()` (fetches the page's `<title>` tag). Users who want to see the actual URL can disable both.

In `components/markdown.tsx`:

1. **`defaultLinkLabel`** — return the raw URL instead of `urlSlugTitleLabel(url)`:
```tsx
const defaultLinkLabel = (url: string) =>
  url.startsWith('mailto:') ? url.replace(/^mailto:/, '') : url
```

2. **`ResolvedLink`** — skip `useLinkTitle()` entirely:
```tsx
function ResolvedLink({ fallbackLabel, t, url }: ResolvedLinkProps) {
  const display = fallbackLabel || defaultLinkLabel(url)
  return (
    <Link url={url}>
      <Text color={t.color.accent} underline>{display}</Text>
    </Link>
  )
}
```

3. **Clean up imports** — remove `urlSlugTitleLabel` and `useLinkTitle` from the `externalLink.js` import.

**Pitfall:** The restore script must include `markdown.tsx` in the overrides list since this file is now customized.

