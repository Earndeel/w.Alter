# Evidence labels for dynamic booking research

## Why this reference exists

Dynamic hotel and transport pages routinely expose a plausible number without exposing the state that produced it. Treat the value, date, item, and availability as separate facts.

## Reusable case pattern

During a Thailand beach search for 17–24 August 2026:

- Google Hotels surfaced **Sea Breeze Bungalow** at a low-end value around **500 THB/night**.
- The property-facing page was then opened directly and visibly showed **“from 1,440 THB”** for one night. It also identified itself as an unofficial booking website.
- The page description supported beachfront wording, while the exact August 2026 inventory was not proven. The correct final label was therefore **live/indicative lead to verify**, not “confirmed under budget”.
- A 12Go route page opened with its calendar on **6 August**, not the requested 17–24 August window. Its route duration and fare range were useful, but the page could not be cited as an exact-date quote until the calendar state was changed and rechecked.

The lesson is not that either lower or higher price is universally correct. The lesson is that a metasearch lead and a property-facing “from” price are different observations until the same dates, room, guests, currency, and inclusions are visible in the same transaction context.

## Minimal evidence record

For every candidate, preserve:

```text
Candidate:
Source URL:
Source type: primary / OTA / metasearch / editorial / forum
Observed at: date + timezone
Dates visibly applied:
Guests / rooms / product:
Exact displayed price:
Price semantics: from / nightly / total / tax-inclusive / package
Availability visibly shown: yes / no
Hard-constraint wording:
Independent cross-check:
Final evidence level: confirmed / live quote / indicative / rejected
Reason for downgrade or rejection:
```

## Dynamic-page checklist

1. Read the visible date fields, not only the URL.
2. Verify checkout after every keyboard or calendar action; focus can remain on the other date.
3. Confirm the room/product-level amenity, not only the property-level amenity.
4. Distinguish `beachfront`, `beach access`, `near beach`, and marketing names such as `by the sea`.
5. Record whether a transport fare includes ferry, terminal transfer, local taxi, park fee, baggage, or only one leg.
6. If the page cannot expose these facts, report the limitation and keep the candidate in the lead section.

## Reporting language

Prefer:

> “The source displayed X THB as a starting price, but exact-date availability was not visible; treat it as an indicative lead.”

Avoid:

> “This hotel costs X THB and is available.”

unless the booking flow visibly proves both claims for the requested state.
