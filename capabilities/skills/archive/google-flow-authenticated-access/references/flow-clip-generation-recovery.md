# Flow connected-clip recovery and QA

Use this reference for a connected advertising video built as two Flow renders (A = 0–10 s, B = 10–20 s) when the project contains duplicate candidates, a late render failure, or a continuation asset that must be selected precisely.

## 1. Keep the operation bounded

1. Authenticate and verify the live account before any credit-consuming action. Record the intended model, duration, aspect ratio, variant count, and project scope.
2. Create one fresh project for the run. Preserve the exact prompts in local text files, but type each prompt into Flow as one single-line string; never send newline characters through the keyboard-event endpoint.
3. Submit A first. Do not start B until A exposes a new media ID, the authenticated binary export returns an MP4, and `ffprobe` plus a contact sheet pass.
4. If Flow produces an unacceptable visual defect, use a new prompt version with the defect named explicitly. For example, replace any request for reserved negative space with: `the entire frame remains real greenhouse footage; no white banner, blank rectangle, lower-third card, or graphic overlay`.

## 2. Select the correct continuation asset

Flow can show several rows with the same generated title. A title is not an identifier.

1. Open `add_2` with a fresh visible coordinate when a semantic click does not open the picker.
2. Capture a fresh snapshot. Enumerate the visible video options and inspect the underlying DOM `<video src>`/`currentSrc` media redirect names or tile links; map the desired media ID to the option before clicking.
3. Click the option. For a video, this may only open a preview and expose `00:10:00`, playback, and `Ajouter au prompt` controls.
4. Capture another fresh snapshot and click the current `Ajouter au prompt` button. Do not assume that selecting the row attached it.
5. Confirm the composer contains the attachment chip/preview (`videocam`) and that the expected source media ID is present in the composer DOM before typing B.
6. If the root grid is stale, reload the project and inspect the actual edit page or the media redirect; never infer the candidate from card order alone.

## 3. Preserve direct video mode

Before each paid submit, a fresh snapshot must show:

- `Agent` with `aria-pressed=false`;
- `Vidéo · 10s`;
- `crop_9_16`;
- `1x`;
- an enabled `Créer` button;
- the complete single-line prompt in the contenteditable;
- the intended attachment.

The failed-card `Réutiliser le prompt`/undo control can open an Omni Flash edit composer whose placeholder is `Décrivez vos modifications`. That is not the direct video composer. Do not submit it as the retry for a two-part 10-second ad. Return to the project’s direct Créer composer, reselect the video mode and attachment, and recheck every setting.

## 4. Poll without false success

Flow’s accessibility snapshot can embed a percentage inside a longer card line. Parse any `\d+%` occurrence, not only a line that consists solely of digits and `%`.

- A progress value is not a media ID.
- `ready`, a play icon, a success-looking prose response, or a thumbnail is not an exported file.
- A card that reaches 99% and then shows `Échec` is not usable and must not be assembled.
- After a failure, allow at most one controlled retry in direct video mode. Avoid blind duplicate submissions; first inspect whether a new media ID or a client-error card already exists.
- Stop when the bounded retry fails or when no new media ID appears after the normal render window. Report the blocker instead of fabricating B or silently assembling A twice.

### 4a. Recover from a stale route after a late failure

A late `Échec` can leave Flow on an edit URL or a media-library view. A poller may then report `progress=none videos=[]` even though the project has not been re-opened in its direct generation context. Treat that output as a route/state diagnostic, not as proof that no render exists:

1. Capture the current URL and a fresh semantic snapshot. If the page is `/edit/<asset>` and the prompt placeholder is `Décrivez vos modifications`, do not use that editor for a direct 10-second retry.
2. Return to the project root (or use the visible `Retour aux projets` path), reopen the same project, and confirm the direct `Créer` composer is visible.
3. Reopen the media picker and identify duplicate-title candidates by their underlying `currentSrc`/media redirect ID, not title or card order. Selecting a row may only open a preview; click the fresh `Ajouter au prompt` control and verify the `videocam` attachment in the composer.
4. Recheck `Agent=false`, `Vidéo · 10s`, `crop_9_16`, `1x`, the full single-line prompt, and an enabled `Créer` button. Submit at most one bounded retry.
5. Poll the project snapshot for embedded percentages and explicit failure text, then export only the new completed media ID through the authenticated binary route.

A successful candidate must satisfy all gates:

1. fresh media identifier in the current project;
2. `/tab/fetch-binary` through the authenticated Playwright context returns HTTP 200 and actual MP4 bytes;
3. `ffprobe` confirms the expected duration, dimensions, video codec, and audio stream;
4. contact-sheet review confirms identity/location continuity, no generated text/logo/watermark, and no major temporal or anatomical artifacts.

## 5. Assemble only after both clips pass

Use the verified A and B files, not browser thumbnails. Inspect frames around the splice, especially A’s final 0.5 s and B’s first 0.5 s. Prefer filter concat with controlled H.264/AAC re-encoding when raw concatenation reports DTS or duration drift. Run `ffprobe` again on the final 20-second MP4 and retain the two source IDs, measured media facts, and QA result alongside the output.
