# Dynamic page extraction reference

## Reusable checklist

- Confirm the live page with `browser_navigate`.
- Capture a full accessibility/DOM snapshot and record the visible URL-selected model, controls, tabs, pricing, and footer.
- If clicking a tab appears to succeed but the snapshot still shows the original panel, verify visually with `browser_vision`; do not infer state from the click response alone.
- For long pages, use the page HTML as a secondary extraction source. Parse:
  - visible semantic text and headings;
  - tables and benchmark rows;
  - hidden FAQ/accordion answers;
  - JSON-LD (`HowTo`, `SoftwareSourceCode`, `FAQPage`, product metadata);
  - links, images, and video sources.
- Preserve UI inconsistencies. URL query state and initial widget state may differ.
- Distinguish platform pricing from official-provider prices and from marketing claims.
- Write a Markdown artifact rather than flooding the chat; include the source URL and extraction scope.

## Kie.ai GPT-5.6 smoke observations

Source tested: `https://kie.ai/gpt-5-6?model=gpt-5-6-sol`

- Header identifies `gpt-5-6-sol`, with Commercial use and Run with API.
- The page describes Sol, Terra, and Luna as a three-tier family.
- The Playground initially showed `gpt-5-6-luna` despite the `model=gpt-5-6-sol` query; a model selector exposed all three IDs.
- Tabs were Playground, Similar, README, and API. The live click response alone was not sufficient to prove panel switching; visual/snapshot verification was required.
- The page exposed Sol platform pricing of 280 input credits/1M tokens, 28 cached-input credits, 350 cache-write credits, and 1680 output credits, while the editorial comparison table separately listed OpenAI official prices.
- The page embedded a structured API example using `POST https://api.kie.ai/codex/v1/responses`, Bearer authentication, model `gpt-5-6-luna`, streaming, input messages, and an empty tools array.
- The README and JSON-LD contained benchmark tables, five integration steps, and nine FAQ answers; hidden accordion content must be included when the user asks for a complete extraction.
