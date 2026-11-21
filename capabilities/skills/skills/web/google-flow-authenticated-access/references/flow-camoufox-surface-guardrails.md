# Flow on Camoufox — interaction-surface guardrails

Use this reference for authenticated Flow generation when the task must remain headless and must not create browser windows on the user's Mac.

## Surface-consent gate

1. Treat headless Camoufox Max as the default interaction surface.
2. Refreshing cookies from a browser database over SSH is not permission to open that browser. Cookie provenance and UI surface are separate decisions.
3. Do not start a dedicated Mac Brave/CDP instance unless the user explicitly authorizes a visible Mac fallback in the current task.
4. If a dedicated instance was started without authorization, close that instance gracefully with the CDP `Browser.close` command and verify the configured debug port is closed. Merely disconnecting Playwright can leave the browser window alive. When a direct CDP WebSocket rejects its generated `Origin`, connect without an Origin header (for example, `suppress_origin=True`) and send `Browser.close`.
5. Never close or restart the user's main browser.

## Headless authentication refresh

- Copy the live Brave `Cookies` SQLite database through SSH using SQLite's backup API; do not open Brave or copy the live file directly.
- Decrypt only in memory with the vault-held key and never log values.
- Require `SIDCC`, `__Secure-1PSIDCC`, and `__Secure-3PSIDCC` before injection.
- Inject the complete filtered Google cookie set into `/session/cookies` **before** creating the Flow tab.
- Prove authentication from a fresh snapshot: profile avatar plus `PRO`, no sign-in CTA, and the literal credit-balance label when credits matter.
- A missing or empty persistent `storage-state.json` is not evidence that the account is logged out; refresh and inject fresh cookies into the active session rather than changing surfaces.

## Flow controls that require real pointer/keyboard events

Flow uses Radix portals and Slate editors. For these controls, DOM `.click()` can return success without opening the visible portal.

- Measure a fresh `getBoundingClientRect()` and call `/tab/click-at` for Radix buttons/tabs.
- Do not confuse the top toolbar **Afficher les paramètres** button (display/grid settings) with the composer generation-settings button showing the current model/aspect/variant count.
- In the composer menu select and re-read the live state: `Vidéo`, `Ingrédients`, required aspect ratio, duration, and `x1`; verify the displayed credit cost before submission.
- Focus the visible Slate `[contenteditable=true][role=textbox]`, click its fresh rect, then use `/tab/keyboard-type` with a single-line prompt. Compare the editor text to the source prompt (length plus SHA-256 is a useful exact-copy gate) and require the Create button to be enabled.

## Multiple continuity references

The media picker behaves as a single selection per open dialog even though the composer can hold multiple attachments.

1. Open the picker, select exactly one asset, verify `aria-selected=true`, click `Ajouter au prompt`, and verify its attachment chip.
2. Reopen the picker for each additional video or storyboard image.
3. Uploading a new local image can reset the current selection. Re-check `aria-selected` immediately before `Ajouter au prompt`; never rely on the row order or prior selection.
4. For a generated continuation, attach the preceding completed video first, then add the shot/action reference image in a second picker pass.
5. If no file-upload route exists, use the verified `File` + `DataTransfer` + bubbling `input`/`change` pattern from `flow-local-media-upload.md`.

## Completion and export

- Poll the project/composer route for a new video media ID; an upload card can show `Échec` while a separate generation card is still progressing, so bind status to the generation card/media ID rather than searching the whole body for one word.
- Primary export path: `/tab/fetch-binary` in the same authenticated Camoufox context.
- Fallback when that route is unavailable: create a second tab in the same `userId`, navigate it to the `media.getMediaUrlRedirect` URL, then inspect `location.href`. A media-document navigation can surface an HTTP/server error while still having followed the authenticated redirect. Accept only a signed `https://flow-content.google/...` URL, download it before expiry, and close the secondary tab.
- A render is deliverable only after the downloaded file passes `ffprobe` and representative frames pass visual QA. For native speech, also transcribe the audio before generating the continuation.
