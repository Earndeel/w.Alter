# Verified Google Flow / Camoufox Max Procedure

This reference records the verified browser path from an authenticated Flow project to a downloadable Omni Flash video. It is a provider-specific implementation of `authenticated-media-generation`; keep the main workflow provider-neutral.

## Active UI/API contract

The working Camoufox Max service exposed these routes on the local proxy:

- `POST /tab/snapshot` — returns the current accessibility tree and fresh `eN` refs.
- `POST /tab/click` — clicks one current ref and returns a post-action snapshot.
- `POST /tab/type` — types into one current ref.
- `POST /tab/evaluate` — evaluates synchronous JavaScript in the page.
- `POST /tab/fetch-binary` — fetches a URL inside the authenticated tab context and streams the response back.

Payload fields are the active session’s `userId`, `tabId`, and, for binary fetch, `url`. Confirm the actual service contract before using these routes in a different deployment.

## Verified Flow sequence

1. Open the authenticated Flow project through the current Camoufox session. If the page is on the project list, inspect the current DOM: the project card’s decorative `div` may not be clickable, while its descendant `<a>` is.
2. Take a snapshot and type the complete prompt into the current editor.
3. Open the media picker. For each input:
   - select the card by exact filename;
   - wait for the selected preview to show that filename;
   - click the current `Ajouter au prompt` action;
   - wait for the picker to close or rerender, then take a fresh snapshot.
4. Verify that all unique filenames appear as chips under the same composer ancestor as the prompt. In the verified run the input order was `_1` environment, `_2` character A, `_3` character B.
5. Verify the current `Créer` control reports `aria-disabled="false"`. A previous disabled state was caused by inputs that were visible in the library but not actually attached to the composer.
6. Click `Créer` once. In Agent mode, Flow replied with a confirmation such as:

   > I'm going to generate a 10-second video ... with Omni Flash.
   > Voulez-vous que je lance la génération de cette vidéo (1), qui coûtera 15 crédits ?

   The first click is only preparation; no billable generation has started yet.
7. Re-snapshot the agent response and locate the exact current DOM element whose visible text is `Accepter`. The verified response exposed it as a generic instrumented element, not a native button. Click `Accepter` for a one-time authorization only. Do not click `Approuver et ne plus demander` unless the user separately authorizes persistent future approval.
8. Poll until a new media identifier/URL appears. Ignore old `Échec` labels in the project/library history unless they belong to the current media ID. A hidden `<video>` template can exist before the media is playable.
9. Use the authenticated binary proxy against the current media redirect:

   ```python
   media_url = (
       "https://labs.google/fx/api/trpc/"
       "media.getMediaUrlRedirect?name=<media-id>"
   )
   response = requests.post(
       "http://127.0.0.1:9377/tab/fetch-binary",
       json={"userId": user_id, "tabId": tab_id, "url": media_url},
       timeout=300,
       stream=True,
   )
   response.raise_for_status()
   with output_path.open("wb") as output:
       for chunk in response.iter_content(1024 * 1024):
           if chunk:
               output.write(chunk)
   ```

10. Check `Content-Type` and size before declaring success. For video, run:

   ```bash
   ffprobe -v error \
     -show_entries format=duration,size,format_name:stream=index,codec_name,width,height,r_frame_rate \
     -of json output.mp4
   ```

   Extract a frame with `ffmpeg` and inspect it when the requested characters/scene matter.

## Failure patterns captured from the verified run

- **Async evaluate returned `{}`:** an async IIFE was serialized as an unresolved Promise. Split it into synchronous evaluate calls and use explicit waits.
- **Stale ref returned HTTP 400:** Flow had already rerendered. Snapshot again; the selection may have applied and the new `Ajouter au prompt` ref may differ.
- **Old ref navigated away:** a ref from a prior composer state activated the wrong control and returned to the project list. Reopen via the current anchor and discard all old refs.
- **Create stayed disabled:** the prompt text was present, but the media library assets were not all attached. Verify composer-local chips, not global filename occurrences.
- **Video element remained hidden:** `currentSrc` alone is not a playable artifact. Fetch the current media redirect through the authenticated tab and validate the returned MP4 with `ffprobe`.

## Artifact acceptance criteria

A verified output must have:

- HTTP 200 from the authenticated binary fetch;
- a video content type and non-zero byte count;
- a valid MP4/container signature;
- duration, codec, dimensions, frame rate, and audio presence checked against the request;
- a visual preview check when scene identity is part of the deliverable.
