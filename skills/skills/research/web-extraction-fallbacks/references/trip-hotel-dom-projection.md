# DOM projection for dynamic hotel lists

Use this reference when network interception returns only configuration/analytics but the rendered hotel cards contain the business records.

## Diagnosis

A successful HTTP response and a large JSON body are insufficient. For the Trip.com hotel-list shape observed in a real Webtop CDP session, hotel records were rendered in repeated `.list-item` cards while the captured JSON candidates did not satisfy the hotel field contract.

Probe the rendered DOM only after JSON candidates fail semantic validation. Keep the same `ExtractionSpec` and scorer so a DOM result is accepted only when it yields required fields and records.

## Profile projection

Observed selectors:

- repeated card: `.list-item`
- hotel name/link: `.hotelName` (also probe `.hotel-title a`)
- identity: `.hotel-card` `id` or `data-offline-hotelid`
- room type: `.room-name`
- rating: `.comment-score` or a class containing `rating`
- nightly price: `.sale`
- total price: `.price-highlight` or `.price-explain`
- location: the line ending in `Show on Map`
- availability: `Check Availability`, excluding `Sold out`/`No rooms`

A profile should emit canonical values with explicit meaning:

- `price` and `total_price`: total including taxes/fees when present;
- `nightly_price`: room/night price;
- `price_basis`: `total` or `nightly`;
- `availability`: boolean;
- `rooms_left`: numeric hint, never a substitute for availability.

Do not put `nightlyPrice` and `roomsLeft` in the generic aliases for `price` and `availability` respectively. Alias collisions can pass the presence check while returning the wrong semantic type/value.

## Hydration and early-exit guard

Dynamic cards can expose required values before links and identifiers are hydrated. A DOM probe must not stop solely because required fields are present. For a hotel profile, continue short, bounded probes until at least one record has a real detail URL; if a site never injects it, use only a canonical detail path derived from an observed site route and an observed card ID, then verify that URL in the browser.

Deduplicate repeated DOM snapshots, but do not discard a later snapshot merely because its record count is unchanged: it may contain enriched URLs, totals, or availability state.

## Validation

Run the explicit DOM/backend diagnostic, then the full chain:

```bash
/root/.hermes/bin/universal-scraper \
  --url 'https://www.trip.com/hotels/list?city=359&searchWord=Bangkok' \
  --profile hotel-availability --mode webtop --pretty

/root/.hermes/bin/universal-scraper \
  --url 'https://www.trip.com/hotels/list?city=359&searchWord=Bangkok' \
  --profile hotel-availability --mode auto --pretty
```

Verify `route`, `attempts`, record count, source paths, URL presence, and distinct total/nightly and availability/rooms-left fields. A valid page title, HTTP 200, or visible cards without the semantic contract is not a successful extraction.
