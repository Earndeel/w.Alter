# Dynamic model-pricing page verification

## Reusable pattern

A model catalog can contain a row even when the scraper has no price record. Resolve the
provider slug to an explicit model-detail URL, fetch that URL, and classify two facts
independently:

- `page_exists`: the model page resolves successfully;
- `pricing_verified`: exact input and output rates are present and parseable.

Recommended operational statuses:

- `verified_rates`: page exists and exact input/output rates were extracted;
- `unverified`: page exists but the price is absent, placeholder text, request-based, or
  otherwise not parseable;
- `not_found` / `not_mapped`: no page could be resolved after slug normalization;
- `fetch_error`: the page check failed operationally.

Never turn a present page with missing rates into `not_found`, and never infer its rate
from a neighboring model family.

## Evidence pattern from Kie.ai

On the 2026-07-31 live check:

| Model | Direct page | Rendered pricing evidence | Classification |
|---|---|---|---|
| Grok 4.5 | `https://kie.ai/grok-4-5` | `Input 160 credits / 1M tokens (≈ $0.8)`, `Output 480 credits / 1M tokens (≈ $2.40)`, plus a stated `+10%` top-up | `verified_rates` |
| Claude Opus 5 | `https://kie.ai/claude-opus-5` | `Pricing: wocx`; no exact input/output rates | `unverified` |

The Grok page had HTTP 200 and the rendered page, while the existing AA slug was
`grok-4-5`; the omission was a mapping defect, not evidence that Kie lacked the model.

## Pricing comparison fields

Keep these independent in the normalized row:

1. exact provider input/output rates;
2. any discount claim written in page copy;
3. provider-published official-price basis, if exposed;
4. external AA reference price and blended delta.

If exact-rate arithmetic disagrees with the page claim, retain both and mark a pricing
conflict. A positive or negative delta versus AA does not prove the same discount versus
the provider's official-price basis.

## Validation checklist

- [ ] direct model URL is stored;
- [ ] slug variants are normalized before `not_found`;
- [ ] HTTP/rendered-page evidence is checked;
- [ ] exact input and output rates are both present before `verified_rates`;
- [ ] page claims and computed discounts are not collapsed into one number;
- [ ] retrieval timestamp is stored for dynamic pricing.
