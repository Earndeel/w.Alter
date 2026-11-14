# Branded static-ad production

Use this workflow when a client thread contains a visual reference, voice-note refinements, and a request for several exact-size brand variants. The generated photo layer, deterministic typography, exact brand assets, and QA evidence are separate concerns.

## 1. Normalize the live brief

Inspect the direct client source before relying on session history. Read from the original request through the newest message, download the referenced image, and transcribe any voice note before designing. Reduce the evidence to one explicit contract:

- deliverable count and exact pixel dimensions;
- aspect ratio and export format;
- brand-to-dominant-color mapping;
- shared approved claims, date, CTA, and required legal markers;
- elements that must stay similar across the set;
- elements that must differ structurally, not merely by recoloring.

Treat “same style, but not exactly the same” as **shared information hierarchy plus distinct composition**. A recolored duplicate does not satisfy it.

### Decision lock for evolving client threads

Client voice notes often contain brainstorming (“je me demande si…”, “peut-être…”) beside actual instructions. Build a compact decision ledger before spending generation credits:

- **locked:** explicit request or later confirmation;
- **tentative:** option being considered, not yet selected;
- **superseded:** contradicted by a newer message;
- **delivery-gated:** ready internally but not authorized for the client.

The newest explicit correction wins over earlier copy, references, and agent recommendations. Brand architecture, deliverable count, and whether a campaign mark is present are material decisions: if they remain tentative, confirm them with the user before generating a whole batch. Do not convert an agent recommendation into the client’s decision.

## 2. Choose the composition mode explicitly

### Deterministic-copy mode (default)

Generate only the photographic/product background. Prompt for the required product placement and negative space, and explicitly forbid all text, numbers, logos, labels, UI, badges, signage, and watermarks. Reject malformed product geometry or accidental markings before layout work.

Add every exact element afterward in HTML/CSS or another deterministic compositor:

- official logo asset;
- approved copy with accents and punctuation preserved;
- price and footnote markers;
- deadline/date;
- CTA and disclaimers;
- flags, icons, and color system.

### Native-final-composite mode (explicit user choice)

When the user explicitly asks an image model such as GPT Image to integrate logos, copy, prices, CTA, shadows, and materials directly into the pixels, honor that choice; do not silently fall back to HTML/CSS composition. For each variant:

1. supply the approved brand creative as a style reference and a separate real-product reference;
2. give an exact text whitelist and an explicit forbidden-text/forbidden-brand list;
3. specify safe margins and the requested aspect ratio;
4. inspect the full-resolution output line by line for accents, numbers, logos, duplicate words, hidden legacy copy, and malformed product geometry;
5. reject or regenerate any attractive-looking image with incorrect commercial copy.

Native composition trades deterministic text guarantees for more organic visual integration. State that trade-off only when relevant; the user’s explicit mode selection governs the workflow.

## 3. Resolve brand logos by entity, not acronym search

Short brand names and acronyms frequently resolve to unrelated organizations. Search-result filenames are not proof of identity.

Preferred resolution order:

1. official brand newsroom, press kit, or identity portal;
2. Wikidata entity claim `P154` (logo image), then resolve that exact filename through Wikimedia Commons;
3. the brand’s encyclopedia infobox asset when a full current lockup is absent from `P154`;
4. another reputable asset source only after independent visual verification.

Render all candidate SVG/PNG files into a labeled contact sheet and visually confirm the emblem, wordmark, current identity, transparency, crop, and proportions before composition. Preserve official logo colors even when the surrounding campaign uses a different dominant color.

Observed durable trap: an acronym filename can look authoritative while belonging to a completely different organization. The fix is entity-ID lookup plus pixel verification, not another blind search.

## 4. Render at the real delivery size

Use a fixed-size canvas (for example, a CSS element whose width and height equal the required export) and render each variant at device scale 1. Screenshot the creative element itself, not an arbitrarily resized browser page.

Before export, run a DOM geometry audit for every creative:

- bounding box equals the requested dimensions;
- `scrollWidth` and `scrollHeight` equal the canvas;
- no descendant extends beyond the canvas;
- every image has loaded with non-zero natural dimensions;
- no console or page errors occurred.

A source background may be lower resolution than the export; report that honestly. “2160×3840 output” describes the delivered canvas, not necessarily native photographic detail.

## 5. QA in two passes

1. **Contact-sheet pass:** compare the whole set for color mapping, hierarchy, product visibility, brand differentiation, and accidental near-duplicates.
2. **Individual full-resolution pass:** inspect each logo, date, accents, price, footnote markers, CTA, legal copy, clipping, product geometry, and AI artifacts.

Inspect fine print separately at the final export scale. Legal text that exists in the DOM but disappears against a pale floor or photo has failed. Fix contrast and re-render, then verify the revised crop.

Finish with actual dimensions, file sizes, checksums when useful, and an archive integrity test.

## 6. Revision semantics and client-delivery gate

Treat revision language literally:

- **“remove X / keep everything else”** permits a localized edit or inpaint;
- **“stop everything / restart / redo the whole thing / make it more polished”** requires a fresh composition. Use rejected work only as a style reference; do not salvage it through cosmetic cleanup;
- **“same style as the previous campaign”** means preserve campaign DNA (hierarchy, spacing, palette, CTA grammar), not legacy product copy or obsolete badges;
- explicit exclusions such as “no flag” or “no campaign mark” belong in both the positive brief and the forbidden-elements list.

Generation completion is not delivery authorization. Keep client-bound assets staged until the user explicitly approves the exact batch for external sending. Before delivery, name the files so variants cannot be confused (for example, brand + concept A/B + resolution), QA every included variant again, and state exactly which set will be sent. When the user requests both current and earlier alternatives, do not assume rejected or obsolete assets are acceptable: use only versions that satisfy the latest locked brief.

For API-based delivery, an accepted upload or pending message ID is not proof of receipt. Verify the client-side chat contains the introduction and every exact attachment filename before reporting success.