# Kie.ai dynamic pricing-table extraction

## Proven contract

For the public Kie pricing page, use the page as discovery and the table API as the structured source:

```text
Page:     https://kie.ai/pricing
Endpoint: POST https://api.kie.ai/client/v1/model-pricing/page
Body:     {"pageNum": 1, "pageSize": 100, "modelDescription": "", "interfaceType": ""}
```

The endpoint returns `data.records` plus `data.pages`. Fetch every page, not only page 1. Records expose `modelDescription`, `interfaceType`, `provider`, `creditPrice`, `creditUnit`, `usdPrice`, `falPrice`, `discountRate`, `anchor`, and `discountPrice`.

- `usdPrice` = Kie price.
- `falPrice` = comparison/reference price shown by the table.
- `discountRate` = Kie's declared discount.
- `modelDescription` contains one charge direction per row, usually Input, Cached Input, Cache Writes, or Output.

## Normalization

1. Keep the original `modelDescription` for evidence.
2. Take the model family before the first comma.
3. Normalize case, dots, spaces, slashes, and underscores to hyphens (`Gemini 3.7 Flash` → `gemini-3-7-flash`).
4. Group records by normalized family.
5. Assign each direction independently; verify a family only when both Input and Output are present.
6. Missing rates are `unverified`, never zero.
7. Keep page existence, rate availability, marketing discount, and computed discount as separate fields.

A model detail page can contain a placeholder or unusable pricing text while the public pricing table has exact rates. Therefore, “page parser returned no price” is an extraction result, not a data conclusion. Query the pricing table before reporting `not_found`.

## Verified audit fixtures (2026-08-15)

| Family | Kie input / 1M | Cached input / 1M | Kie output / 1M | Declared discount |
|---|---:|---:|---:|---:|
| `grok-4-6` | 0.80 | 0.20 | 2.40 | 60% |
| `gemini-3-7-flash` | 0.225 | — | 1.125 | 70% |
| `claude-opus-5` | 2.00 | — | 10.00 | 60% |

These are audit fixtures, not a substitute for a fresh fetch.

## Validation pattern

- Assert HTTP success and API `code == 200`.
- Assert `records` is non-empty and `pages` is traversed completely.
- Assert the target family appears with both required directions.
- Compare the table's declared discount with the blended computed discount when a reference price exists.
- Preserve the catalog endpoint URL and retrieval timestamp in the output.
- If a downstream benchmark translates task cost from token prices, label it as an estimate and keep its Pareto surface separate from the benchmark's native cost surface.
