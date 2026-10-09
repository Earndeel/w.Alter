# Flow: upload a local generated reference through the actual UI

Use when Camoufox's active tab contract has no file-upload endpoint and Flow creates a detached file input on its visible Upload media button. Prefer a documented native file-chooser tool when available. This method feeds a real File to the observed input and preserves the application's normal upload handlers; do not guess backend endpoints.

1. Open the live ingredient picker and locate Upload media from a fresh snapshot.
2. In that tab only, temporarily wrap `HTMLInputElement.prototype.click`. Capture `this` when `this.type === 'file'`; call the original method for other inputs. Store the original method and captured input in task-specific temporary window properties. Suppress only the native file dialog for the captured file input.
3. Click the real Upload media button via its current accessibility ref. Verify that an input was captured and that its `accept` allows the exact file type.
4. Transfer the authorized local file's bytes as base64 within the private tool call, construct `new File([Uint8Array.from(atob(b64), c => c.charCodeAt(0))], filename, {type: mime})`, add it to a `DataTransfer`, assign `input.files = transfer.files`, and dispatch a bubbling `change` event.
5. Restore the original prototype and delete temporary window properties in `finally`, including on capture or upload failure. Never leave the hook installed.
6. Read back the exact uploaded filename/type from Flow's asset picker, select that asset, add it to the prompt, and verify its real media ID, thumbnail readiness and absence of `error` icons before generation. A successful DOM event is not proof of upload or binding.

If multiple video ingredients show a chip error or are silently omitted on Reuse prompt, do not claim both were bound. For character continuity, an extracted frame from the already approved secondary clip can be uploaded as an image alongside the primary video; verify the actual chips again. This is input-shape recovery, not proof of the provider's formal reference limit.

For failed generations, distinguish the old failure card from the retry. Record the pre-submit failure count, require a new success asset ID, and detect new `failed to generate` text. Confirm a live account balance before claiming a failed job was not charged; never infer a debit or refund solely from UI prose.
