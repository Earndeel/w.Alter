---
name: google-flow-authenticated-access
description: Authenticated Google Flow access through fresh Mac Brave cookies and Camoufox Max, including safe account/credit verification and controlled UI operations. See `references/flow-video-generation-guardrails.md` for the verified generation gate.
version: 1.0.0
author: W.Alter
triggers:
  - Google Flow
  - google labs Flow
  - ouvrir Flow
  - mon compte Flow
  - crédits Flow
  - générer dans Flow
  - utiliser mes crédits Flow
metadata:
  hermes:
    tags: [google-flow, browser, cookies, camoufox, authenticated-access, video-generation]
---

# Google Flow Authenticated Access

Detailed Gemini Omni generation workflow: `references/gemini-omni-flow-video-generation.md`.

Use this skill when Monsieur asks to inspect or operate his Google Flow web
account. It covers the authenticated browser path, account/credit checks, and
safe handoff to a generation workflow. It does not replace a product brief or
claim-verification workflow.

## Operating principle

Separate **access verification** from **credit-consuming actions**. A live
account check must not create a project, submit a prompt, or start a render.
Report the exact credit balance only after it is visible in a refreshed live
snapshot. Never infer credits from the `PRO` badge, a bonus banner, or a prior
session.

## Canonical runtime

Prefer the active host-side Camoufox Max service:

- Base URL: `http://127.0.0.1:9377`
- Preflight: `GET /health`; require HTTP 200 and JSON `ok: true`
- Current API uses singular routes: `/session/...` and `/tab/...`
- Use Webtop `9378` only when the host service is unavailable or the task
  explicitly requires the real Chromium/CDP fallback

### Interaction-surface consent (mandatory)

- Run Flow automation in **headless Camoufox Max by default**, including cookie refresh, project work, generation, polling, and export.
- Never launch, connect to, or create tabs in a Mac browser merely because it is an available fallback. A documented fallback is not user consent.
- Use a Mac-visible Brave instance only when Monsieur explicitly authorizes that surface for the current task. “Camoufox only” is a hard workflow constraint.
- Cookie provenance does not determine the interaction surface: reading a fresh Brave cookie database over SSH is headless and acceptable; opening Brave windows is a separate side effect requiring consent.
- If an unauthorized dedicated Mac instance was started, close that dedicated instance gracefully through CDP `Browser.close` and verify its debug port is closed. Never disturb the main browser.

The tested consent, recovery, Radix-control, multi-reference attachment, and export details are in `references/flow-camoufox-surface-guardrails.md`.

Canonical lifecycle endpoints:

- `POST /session/cookies` — `{userId, cookies}`
- `POST /tab/new` — `{userId, listItemId}` → `tabId`
- `POST /tab/navigate` — `{userId, tabId, url}`
- `POST /tab/snapshot` — `{userId, tabId}`
- `POST /tab/screenshot` — `{userId, tabId}` → base64 PNG in `buffer`
- `POST /tab/click` — `{userId, tabId, ref}`
- `POST /tab/type` — `{userId, tabId, ref, text}`
- `POST /tab/keyboard-type` — `{userId, tabId, ref, text}`; sends real keyboard events to Flow's Slate/contenteditable editor
- `POST /tab/click-at` — `{userId, tabId, x, y}`; clicks a freshly measured visible coordinate when a semantic ref is present but does not trigger the visible portal/button
- `POST /tab/evaluate` — `{userId, tabId, expression}`
- `POST /tab/close` — `{userId, tabId}`
- `POST /tab/fetch-binary` — `{userId, tabId, url}`; transfers a Google media response through the authenticated Playwright context. The managed route must remain host-restricted to `labs.google` and `*.googleusercontent.com`.

## Authenticated Flow check

1. Run the health check before touching cookies or opening a tab.
2. Copy a fresh Brave `Cookies` database from the Mac. Do not reuse an old
   extract: Google sessions expire and cookie values are fingerprint-sensitive.
3. Query the **complete** Google cookie subset — do not apply a `LIMIT` and do
   not filter by cookie name prefix beyond the analytics exclusions in step 4.
   **Critical:** ensure `SIDCC`, `__Secure-1PSIDCC`, and `__Secure-3PSIDCC`
   are included — these session-integrity cookies are required for Google to
   recognise the session as valid. Without them, every navigation to a Google
   service will land on a sign-in page regardless of the other cookies present.
   Target domains: `google.com`, `accounts.google.com`, `labs.google`,
   `youtube.com`, and any other `%.google%` host. Decrypt on the host with the
   vault-held Brave key. On the verified Mac Brave profile, `encrypted_value`
   uses a `v10`/`v11` prefix followed by an embedded 16-byte IV: strip the
   three-byte prefix, decrypt the remaining ciphertext with AES-CBC using that
   embedded IV, remove PKCS#7 padding and the initial garbage block, then
   retain the printable cookie value. Do not assume the fixed-space-IV variant.
   When querying SQLite over SSH, use a literal separator such as `|`; passing
   `'\\\\t'` can be interpreted literally and silently produce zero parsed
   cookies. Never print cookie values, raw SQL output, or the derived key. In particular,
never dump the in-memory cookie list or return it as JSON from `execute_code`;
log only counts, host counts, and an allow-listed integrity-cookie name check.
4. Exclude analytics/telemetry cookies such as `_ga`, `_gcl`, `_gat`, `_gid`,
   `_dd`, and `_fbp` before injection.
5. Inject the cookie list into a unique temporary `userId`, then create a tab
   with a stable `listItemId` for that check.
6. Navigate to `https://labs.google/fx/fr/tools/flow` (use the current locale
   route when appropriate).
7. Capture a snapshot and verify that the page is authenticated. A `PRO` badge
   and profile avatar are useful indicators, but they are not the credit
   balance. If the task names a newly promoted model, record the exact live UI
   branding rather than paraphrasing it. For example, a homepage heading
   `Introducing Gemini Omni Flash` plus a `Try Omni now` button proves that
   **Gemini Omni Flash** is exposed to the account; it does not prove render
   duration, aspect ratio, variant count, cost, or that a job was submitted.
   Those settings still require a fresh Create-composer snapshot after prompt
   approval.
8. Click the visible `PRO` profile button. Flow renders the profile dialog
   asynchronously; the first snapshot may contain `Chargement…`.
9. Wait several seconds, then call `/tab/snapshot` again. Only accept a balance
   when the refreshed snapshot contains the literal `Crédits Google Flow` plus
   its numeric value. Record any bonus banner separately from the balance.
10. Close the temporary tab with `/tab/close` in both success and failure paths.

The exact verified UI markers and request sequence are in
`references/flow-account-check.md`.

## Media export and output verification

A Flow project can expose multiple `/edit/` links without containing multiple
videos: an edit page may be an image/reference asset. Inspect each edit page and
read the actual `<video>` `currentSrc`; do not infer the asset type from link
count. A generated video may remain at `readyState: 0` in the DOM while its
media redirect is still downloadable through the authenticated context.

For a generated media name:

1. Keep the authenticated `userId` and a live `tabId` from the same Playwright
   context that shows `PRO`.
2. Request the Flow redirect URL through `/tab/fetch-binary`, not with plain
   `requests` or a context-free HTTP client; the latter commonly returns `401`.
3. Save the response only after checking HTTP 200 and `content-type: video/mp4`
   (or the expected image type).
4. Run `ffprobe` on the saved file and report the measured duration, dimensions,
   codec and byte size. Do not call an asset “delivered” merely because Flow
   shows a play icon or a `READY` marker.
5. If the Camoufox service must be restarted, assume the authenticated tab and
   in-memory cookies are gone; refresh and inject Brave cookies again before
   continuing. Avoid restarting an active authenticated service just to add a
   temporary route unless a fresh-cookie recovery path is ready.

The runnable extraction and export details are in
`references/flow-media-export.md`. For the Gemini Omni composer defaults,
rights-consent gate, bounded reference upload, and pre-submission checks, also
consult `references/flow-omni-camoufox-import-quirks.md`.

## Credit-consuming operations

### Prompt validation gate (MANDATORY)

Never submit directly to Flow without user review. Every time Monsieur
requests a video, write the prompt(s) to one or more `.txt` files in
`/tmp/`, present them inline for review, and **wait for explicit
validation** before touching Flow. This avoids wasting credits on
misaligned briefs. Monsieur says "génère" → generate prompts first, not
videos.

Only proceed to Flow after:
- the prompt file is saved and Monsieur has seen the content
- duration, aspect ratio, and number of clips are confirmed
- the script/dialogue matches the brief

Before any generation or project creation:

- confirm the intended asset, duration, aspect ratio, and number of variants
- use the smallest validation render that can answer the quality question
- do not spend the full credit budget merely to test login or UI access
- preserve the exact prompt and the resulting project/render identifier
- verify the output visually before launching variants

For advertising video, use an explicit, time-coded shot list with motivated
cuts and timed segments. Do not submit a prose paragraph that describes one
continuous scene: that routinely produces a static talking-head result. When
the brief asks for a longer ad assembled from short generations, treat the
clips as a connected sequence (for example, A 0–10 s plus B 10–20 s): lock the
actor/location/lighting, make B begin on A's final motion, attach A as B's
continuity reference when possible, and verify both downloaded MP4s before
assembling or delivering the 20-second result. Never combine a multi-shot plan
with contradictory instructions such as `no cuts` or `one continuous shot`.

Default to deterministic post-production for exact brand/legal typography. If
Monsieur explicitly wants Flow-native advertising graphics, first analyze the
reference's graphic system, attach a sanitized style board separately from the
product/identity reference, allow-list every permitted on-screen phrase, and
run pixel-level text QA; “same style” is not permission to copy an official
logo, legal mark, unwanted product, or solar panel from the source. Treat
native dialogue as an exact-copy gate: isolate the approved French line in a
dedicated block, prefer one continuous grammatical sentence when sentence
boundaries trigger ad-libbing, keep the music bed well below a dry studio voice,
and ASR-transcribe each exported clip before submitting its continuation.
When a forbidden visual object survives explicit negatives, redesign the shot
to exclude the whole risk region (for example, frame below the eaves instead of
showing a roof) rather than spending credits on longer negative lists. Product
claims and brand assets must be verified separately before they are embedded
in a prompt. The detailed two-reference, native-voice, motion-graphics and ASR
workflow is in `references/flow-native-voice-motion-graphics.md`. When reporting
a result, explicitly identify the source of visuals, voice, visible subtitles
and music, and label ASR as verification rather than generation; the reference
includes the provenance ledger.

For exact, credit-consuming video work, prefer Flow's **Créer** path rather
than Agent mode when Monsieur asks for a direct prompt submission. Confirm a
fresh snapshot shows the video settings (model, duration, aspect ratio,
variant count) before typing or clicking. For two clips that must start in
parallel, do not assume that two tabs in one project/context create two jobs:
use the bounded parallelism and project-scoping procedure in
`references/flow-connected-ad-video.md`, then verify new media IDs rather than
trusting navigation or a success-looking UI response.

### Exact edit-URL continuation

When Monsieur provides a Flow `/project/<id>/edit/<asset-id>` URL and asks to
continue that video, treat the edit URL as the source of truth. Open it first,
inspect the actual `<video>` `currentSrc`, duration, visible end frame, and
prompt; do not start from the project root's card order. The root can lag behind
or show older male/female assets while the direct edit page is already correct.

For a continuation, use this decision path:

1. On the edit page, inspect the timeline `+` control and try native
   `Prolonger` only when it is enabled for the selected clip. If the clip was
   made with Omni Flash and `Prolonger (Veo 3.1 - Lite)` is disabled, do not
   fight the disabled control: return to the project **Créer** composer and
   attach the original video from the media picker.
2. Verify Agent is off (`aria-pressed=false`) and re-check `Vidéo · 10s`,
   `crop_9_16`, and `1x` immediately before submission.
3. Flow's prompt is a Slate/contenteditable editor. A locator fill through
   `/tab/type` can leave the DOM text visible while React's editor state is
   incomplete, causing an `Application error` at submit. Focus the visible
   contenteditable and use `/tab/keyboard-type` for real keyboard events; use
   a fresh visible button rect with `/tab/click-at` for the final `Créer` click.
   **Never pass newline characters to `/tab/keyboard-type` for the Flow prompt**:
   real Enter events can submit each paragraph as a separate generation, creating
   partial prompt jobs and wasting credits. Compose the full prompt as one
   single-line string (use semicolons and time ranges instead of line breaks),
   type it once, then inspect a fresh snapshot to confirm the complete prompt is
   present before clicking Create. If a long typing request times out, inspect
   the field and job cards before retrying; never blindly type it again.
4. Prefer the actual source video as the reference, not only a saved still. If
   the root grid does not show it, reopen `add_2`; the picker may still expose
   the exact titled video. Select the asset row, verify `aria-selected=true`,
   click `Ajouter au prompt`, and confirm the attachment chip/preview before
   typing. If only a still is available, clean any old watermark from the
   reference first and verify the cleaned image visually.
5. After submission, track progress from `/tab/snapshot`'s semantic/accessibility
   output. Flow's DOM links and `innerText` can hide percentage progress even
   while the accessibility tree shows `40%`; wait until the semantic snapshot
   contains no progress percentage. A completed-looking card may be an isolated
   fragment caused by a bad multiline submission, so select the newest card
   whose prompt contains the full brief and download candidates before choosing.
6. For generated ads, export through `/tab/fetch-binary`; the endpoint may return
   raw MP4 bytes rather than JSON, so save the response body directly after
   checking HTTP 200 and the expected media signature. Run `ffprobe`, extract a
   regular-timestamp contact sheet, and inspect the actual pixels. Flow can
   still add a star/platform watermark despite an explicit negative prompt;
   remove it in post-production with a narrowly scoped interpolation mask and
   visually re-check the masked area before delivery. The repeatable details
   are in `references/flow-ad-video-generation-qa.md`.
7. After submission, verify the page is not on the client-error screen and
   wait for a new media identifier. A progress card can disappear while the
   project refreshes; reload the project and inspect the newest card rather
   than retrying blindly. If several candidate IDs appear, download them
   through `/tab/fetch-binary`, identify the one tied to the newest prompt/card,
   and compare source-end/B-start frames plus regular storyboard timestamps.

The exact continuation recovery and media-selection recipe is in
`references/flow-continuation-recovery.md`.

When the media picker exposes `input[type=file]` but the active Camoufox API has
no `setInputFiles` route, upload a checked local reference by constructing a
browser `File`, assigning it through `DataTransfer`, and dispatching bubbling
`input` plus `change` events. Then select the real asset option and verify the
composer attachment/media ID; a filename in the library is not enough. The
safe pattern is in `references/flow-local-media-upload.md`.

The full connected-ad workflow—including volatile accessibility refs, direct
Create-mode submissions, project-scoped reference assets, queue versus
completed-media checks, the false-success guard, and the
`/tab/fetch-binary` export pattern—is in
`references/flow-connected-ad-video.md`.

The bounded retry, duplicate-title media-picker, and late-failure recovery procedure is in
`references/flow-clip-generation-recovery.md`. In particular: a selected video row may only open a preview; click the fresh `Ajouter au prompt` control and verify the composer has a `videocam` attachment plus the expected `<video>` `currentSrc`. If several rows share the same title, identify them from their underlying media redirect names/currentSrc and fresh DOM order, never from the title alone. A failed card's `Réutiliser le prompt` control may open Omni Flash edit mode with a `Décrivez vos modifications` composer; do not submit that as a direct 10-second video retry. Return to the direct Créer composer and re-assert `Agent=false`, `Vidéo · 10s`, `crop_9_16`, and `1x`.

For polling, search snapshots for embedded percentages (`\d+%`), not only lines that equal a percentage: Flow may place `99%` inside a card line. A percentage reaching 99% followed by `Échec` is not a deliverable; allow at most one controlled direct-mode retry, then stop and report the missing MP4. Avoid prompt language such as `reserve negative space` or `clean CTA composition` unless it also explicitly says the whole frame must remain real footage and forbids white banners, blank rectangles, lower-third cards, and graphic overlays; Flow can materialize the requested empty area as a large white panel.

A poll result such as `progress=none videos=[]` is not conclusive unless the live snapshot is clearly on the project/composer route containing the current generation card. First record `location.href` and inspect the visible route: an `/edit/<asset>` page with `Décrivez vos modifications`, or a media-library page after a failed card, can show no active progress even though the job state is merely stale or the project is refreshing. Return to the project root, reopen the direct `Créer` composer, and inspect the newest card/media IDs before deciding that no render exists. Never submit from the failed-card edit composer; re-assert `Agent=false`, `Vidéo · 10s`, `crop_9_16`, `1x`, the attachment, and the complete one-line prompt before the single bounded retry.

After a retry succeeds, wait for the new media ID, export that exact ID through `/tab/fetch-binary`, and verify the downloaded MP4 before assembling. Do not treat a transient progress disappearance, navigation change, thumbnail, or success prose as completion.

## Hard delivery gate for generated advertising video

Treat the Flow agent's prose as an intent report, never as render evidence.
Messages such as `scheduled`, `in the queue`, or `ready shortly` can coexist
with a visible `Échec` card. A generation is real only when the current page
exposes a new media identifier, the authenticated binary export returns an
actual MP4, `ffprobe` proves the expected streams/duration/dimensions, and
representative frames pass visual QA.

For a connected ad, perform a bounded visual review before transfer: make a
contact sheet at regular timestamps and inspect frames around every splice.
Reject generated legal copy, fake certification marks, brand logos, random
signage, or platform watermarks unless Monsieur explicitly accepts them.
Keep exact legal/brand typography in post-production rather than asking Flow
to invent it. Do not deliver or transfer a technically valid file as final if
its pixels contain hallucinated text or logos.

When joining two nominally identical clips, a concat demuxer may emit
non-monotonic audio timestamps and a duration drift. Prefer filter concat plus
controlled H.264/AAC re-encoding when the raw concat reports DTS warnings or
an unexpected duration; re-run `ffprobe` after the final encode.

## Troubleshooting

- **Sign-in page / missing Flow UI:** refresh the Mac cookie copy and repeat the
  injection; do not ask Monsieur for credentials that are already available in
  the configured browser session. If sign-in persists despite fresh cookies,
  verify that `SIDCC`, `__Secure-1PSIDCC`, and `__Secure-3PSIDCC` are present
  — their absence is the most common cause of silent session rejection.
- **Google password sign-in via Camoufox:** when the Google sign-in page appears
  despite cookie injection, the Camoufox base server (port 9377) does not have
  `/tab/press` or `/tab/key` endpoints. To submit a password: (a) use
  `/tab/click` to focus the password field, (b) `/tab/type` to enter the
  password, (c) find the `Next` button ref in the snapshot and `/tab/click` it.
  Do not attempt to send an Enter key event — it will 404. If two different
  Bitwarden passwords both fail, the password may have been changed; use "Try
  another way" or fall back to a fresh cookie session.
- **`Chargement…` remains:** keep the profile dialog open, wait, and take a
  second or third snapshot. Do not report zero or an unknown balance as the
  account balance.
- **Host Camoufox unavailable:** check `/health` and use the documented Webtop
  fallback only if it is actually healthy. Do not turn a setup failure into a
  permanent claim that browser access is impossible.
- **Modal absent from the snapshot:** use a screenshot or DOM inspection to
  verify the visible state, then return to the semantic snapshot when possible.
- **Remote cookie-backup command breaks under macOS zsh:** `ssh` joins remote
  argv into a command string; sending `python3`, `-c`, and Python source as
  separate post-host arguments can expose semicolons/parentheses to zsh and
  produce misleading syntax or glob errors. Build one remote command instead:
  `remote = "python3 -c " + shlex.quote(python_source)`, then pass that single
  string after the host. Prefer SQLite's `Connection.backup()` into a temporary
  remote database before `scp`, rather than copying the live Brave database.
- **Cleanup failure:** retry `/tab/close`; never leave temporary tabs open
  between tasks because persistent browser contexts consume memory.

## Verification record

For a reusable, rerunnable probe rather than ad-hoc shell commands, consult
`references/flow-account-check.md` and keep the probe read-only by default.
