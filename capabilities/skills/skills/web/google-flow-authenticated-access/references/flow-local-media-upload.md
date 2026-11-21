# Uploading a local reference into Google Flow through Camoufox Max

Use this when Flow's media picker must receive a local image and the active
Camoufox HTTP contract has no dedicated `setInputFiles` endpoint.

## Preconditions

- The Flow tab is authenticated and already inside the intended project.
- The media picker is open from the current composer (`add_2`).
- A fresh DOM check finds a visible or mounted `input[type=file]` with the
  expected `accept` value.
- The local reference has been visually checked for unwanted text, logos,
  watermarks, old end cards, or legal copy that could contaminate generation.

## DataTransfer upload pattern

1. Open `add_2`, then the visible `Importer l'élément multimédia` control if the
   file input is not mounted yet.
2. Confirm the input contract with `/tab/evaluate`:

   ```js
   Array.from(document.querySelectorAll('input[type=file]')).map((e, i) => ({
     i, accept: e.accept, multiple: e.multiple
   }))
   ```

3. Read the local file outside the page, base64-encode it without printing the
   payload, and evaluate a single expression that constructs a browser `File`,
   places it in a `DataTransfer`, assigns `input.files`, and dispatches both
   `input` and `change` with `bubbles: true`:

   ```js
   (() => {
     const bytes = atob(BASE64_BYTES);
     const array = new Uint8Array(bytes.length);
     for (let i = 0; i < bytes.length; i++) array[i] = bytes.charCodeAt(i);
     const file = new File([array], FILE_NAME, {type: MIME_TYPE});
     const transfer = new DataTransfer();
     transfer.items.add(file);
     const input = document.querySelector('input[type=file]');
     if (!input) return {ok: false, reason: 'no file input'};
     input.files = transfer.files;
     input.dispatchEvent(new Event('input', {bubbles: true}));
     input.dispatchEvent(new Event('change', {bubbles: true}));
     return {ok: true, name: input.files[0].name, size: input.files[0].size};
   })()
   ```

4. Wait for upload propagation and take a fresh snapshot. Require the exact
   filename and media type to appear. Select the real `role=option` asset row,
   not its title or thumbnail child.
5. Selection behavior varies: it may attach immediately and close the dialog,
   or expose a fresh `Ajouter au prompt` button. Handle the current state rather
   than assuming one path.
6. Verify the composer contains the attachment chip/preview. Inspect the
   attached image/video `src` and record its `media.getMediaUrlRedirect?name=`
   identifier when present. A filename elsewhere in the library is not proof of
   attachment.

## Guardrails

- Match the MIME type to the file (`image/jpeg`, `image/png`, and so on).
- Keep references reasonably small; base64 expands payload size by roughly one
  third and is sent inside one JSON request.
- Never log the base64 expression, cookies, or authenticated request headers.
- Use one file per controlled upload unless the brief explicitly needs several;
  multiple mounted inputs and stale dialogs make attachment identity ambiguous.
- After upload, re-check direct Create settings and the exact prompt before any
  credit-consuming submit.
