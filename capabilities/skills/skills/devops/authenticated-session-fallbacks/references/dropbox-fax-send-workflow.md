# Dropbox Fax / HelloFax — tested send recipe

## Scope

Use this reference only after the user has explicitly authorized transmission. It records the live UI path verified with the host Camoufox Max API on port `9377`; it does not replace the general cookie/authentication workflow.

## Verified sequence

1. `POST /session/cookies` with freshly extracted, target-domain auth cookies and a new `userId`.
2. `POST /tab/new` → capture `tabId`.
3. `POST /tab/navigate` to `https://app.hellofax.com/`.
4. Verify `location.href`, `document.title`, and body text containing the authenticated greeting plus `Send faxes`.
5. Click the visible `SEND A FAX` control.
6. Upload the PDF; verify its filename appears under `Selected documents`.
7. Click `Next`, fill the recipient field, and verify the normalized country/number suggestion.
8. Click `Send document`. On a first fax, HelloFax may open a modal asking for sender name and attachment preferences; confirm the modal's own `Send document` button.
9. Verify the result page contains `Your document has been sent!`, the recipient, and the document ID.

## Hidden file-input upload

The active HTTP wrapper exposes click/type/evaluate but not a Playwright file-path setter. Upload the local PDF without printing its contents by creating a browser-side `File` and assigning it through `DataTransfer`:

```javascript
(() => {
  const binary = atob(BASE64_PDF);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const file = new File([bytes], 'document.pdf', {type: 'application/pdf'});
  const input = document.querySelector('input[type=file]');
  const transfer = new DataTransfer();
  transfer.items.add(file);
  input.files = transfer.files;
  input.dispatchEvent(new Event('input', {bubbles: true}));
  input.dispatchEvent(new Event('change', {bubbles: true}));
  return JSON.stringify({name: file.name, size: file.size, files: input.files.length});
})()
```

Generate `BASE64_PDF` locally from the requested PDF and send the expression to `/tab/evaluate`; return only filename/size/count, never the base64 or cookies. Re-snapshot after the event because the React UI and refs change asynchronously.

## Verification fields

Useful post-send evidence from the authenticated page:

- success text: `Your document has been sent!`
- status row: `FAXING TO <destination>` or equivalent
- recipient detail: exact normalized fax number
- document ID: often adjacent to the `DOCUMENT ID` label
- stable handles: `Download PDF` or `Preview` link containing the same document GUID
- URL commonly includes `home/manage?success=true`

Treat `Sending` as accepted by HelloFax but still in progress; never report it as delivered to the recipient. Preserve the document ID in the immediate response, then remove transient cookie files and copied Brave DBs.

## Ref discipline and safety

- Re-snapshot after every navigation, upload, and click; `[eN]` refs are not stable.
- Validate the recipient before the final click, not only after submission.
- Do not add a cover page, color mode, or CC recipient unless requested.
- Do not use a stale authenticated tab when the user has explicitly asked to send now; create a fresh session.
- Do not claim success from a `200` click response alone; require the page-level confirmation and a tracking handle.
