# Agentic hotel research: parallel discovery, verification, and judgment

Use this reference when a travel request combines a hard price ceiling, a qualitative lodging requirement, flexible dates, and transport trade-offs. The browser stack is usually already sufficient; the durable problem is orchestration and evidence quality.

## Mission contract

Convert the user's brief into explicit fields before browsing:

- `origin`, `destination_scope`, `date_window`, `stay_length` (4/5 nights), `travellers`, `rooms`, `currency`;
- hard constraints: maximum total/nightly price, exact room attributes, beachfront definition, air conditioning, acceptable transport time/cost;
- soft preferences and weights: direct sea view, quiet, comfort, food, island feel, flexibility;
- tolerances: date flexibility, one-way transport ceiling, maximum door-to-door duration.

If exact dates are absent, search a declared window (for example, departure dates 14–21 days ahead) and state the assumption. Never call a date-sensitive offer confirmed until the target page visibly reflects the intended check-in, checkout, occupants, and room count.

## Execution graph

1. **Planner** — normalize the brief, define hard gates, choose the date grid, and allocate source lanes.
2. **Parallel discovery wave** — separate workers for (a) destination/transport, (b) official hotel prices, (c) OTAs/market discovery, (d) reviews and recurring complaints, (e) location/shoreline, and (f) policies/hidden fees.
3. **Mechanical normalization** — deduplicate properties, align room category, occupancy, nights, taxes, breakfast, cancellation, currency, and capture time. Do this with code where possible, not prose agents.
4. **Targeted verification wave** — revisit only the leading candidates and all fields that are missing, stale, or contradictory. Use direct booking pages for price/availability; use local authenticated browser sessions for personal cookies; do not export those cookies to third-party browser clouds.
5. **Adversarial critic** — attempt to disqualify the shortlist: "near beach" is not "on sand", a sea-view room is not necessarily beachfront, a teaser price may exclude taxes or use a different room/occupancy, and an old photo can hide construction or a changed shoreline.
6. **Repair loop** — for each material objection, run a narrow recheck and recalculate. Do not repeat the whole search blindly.
7. **Judge/synthesizer** — rank only evidence-backed candidates and return distinct labels: best overall, best value, safest booking, and best fallback. Include trade-offs and unknowns, not just a single score.
8. **Pre-book gate** — revalidate the winning offer in the same session immediately before presenting it; require explicit user approval before payment or reservation.

Hermes delegation is wave-based: use parallel subagents for reasoning-heavy lanes and scripts/bulk fetches for extraction. With a three-child concurrency ceiling, schedule additional lanes in subsequent waves instead of pretending that one broad agent performed independent research.

## Adaptive research protocol

### 0. Intake and parameter audit

Before searching, extract a parameter sheet and mark every field `provided`, `inferred`, or `missing`. Ask the user before the first expensive wave when a missing field can change the ranking materially: exact dates versus flexible window, travellers/rooms, total versus nightly budget, whether taxes and transport count, strictness of direct sand/sea view/air conditioning, tolerance for transfers, and whether images of the exact room are required. For low-impact omissions, choose a reversible default, state it, and continue rather than blocking the run.

### 1. Plan the loops

The planner must publish the research graph before delegation: discovery lanes, verification lanes, source hierarchy, date/occupancy grid, normalization schema, stopping conditions, and fallback loops. A loop is not merely another search query; it has a purpose, input, output, and trigger. Typical loops are:

- broad destination and transport discovery;
- property and room-category discovery across official sites and OTAs;
- visual/location verification using room photos, maps/satellite, and independent descriptions;
- price/availability verification for the exact date state;
- door-to-door transport and flight-versus-ground comparison;
- adversarial rejection of false matches and hidden fees;
- alternative generation when the first wave produces fewer than the required number of viable candidates, or when all candidates violate a hard constraint.

### 2. Parallel exploration and convergence

Send independent lanes in parallel, then normalize their outputs into one candidate ledger. Do not let an early attractive property anchor the search. Run at least one alternative loop deliberately designed to find options the initial destination list missed: nearby beaches, different transport modes, local-language queries, direct-property search, and date shifts within the allowed window. Stop only when the target number of verified candidates is reached, the search budget is exhausted, or the remaining candidates are explicitly documented as leads/rejections.

### 3. Clarification checkpoint

After reconnaissance and before costly deep verification, return to the user if the unresolved trade-off changes the answer materially — for example, strict budget versus direct sand, island versus travel time, or flight versus ground. Ask a short targeted question with the concrete observed trade-off and the effect of each answer; never ask the user to choose between abstract research strategies. If the user is unavailable, continue under the declared default and label the result conditional.

### 4. Evidence-backed report

The final report must be easy to scan: a one-paragraph verdict, a comparison matrix, separate verified offers/leads/rejections, explicit trade-offs, and a next-step checklist. Include direct raw links for every important claim and, where visual criteria matter, a compact image set or image URLs showing the exact room/category and the shoreline context. Each image must be tied to a source and capture time; generic property photos cannot prove room compliance.

## Mandatory completion gate — no brochure outputs

A travel-research run is incomplete until the leading candidates have passed a targeted verification wave. The synthesizer must not promote a candidate from `lead` to `verified` using only search snippets, editorial descriptions, or a generic property page.

For every finalist, capture a dated evidence row for:

- exact check-in/check-out, guests, rooms, room category, and live availability;
- final nightly and total price, currency, taxes, fees, cancellation, and what is included;
- room-level air conditioning, sea-view wording, and photos of the exact room/category;
- physical shoreline proof: direct sand access versus road/promenade/steps or a stated walking distance;
- complete door-to-door transport: each leg, departure/arrival points, waiting/transfer time, ferry inclusion, one-way and return cost;
- a flight-versus-ground comparison for any route where flying could plausibly reduce door-to-door time or cost;
- source URL, capture time, evidence excerpt or screenshot reference, and confidence label.

If any hard field is `unknown`, the candidate remains a `lead` and cannot appear in the recommended shortlist. If the page has reset dates, occupancy, or room type, invalidate every price captured in that state and re-run the interaction. If a room image or wording is ambiguous, state the ambiguity and do not infer compliance. The final answer must contain separate sections for `verified offers`, `leads requiring confirmation`, and `rejected candidates`, plus the exact missing checks for each lead.

## Evidence contract

Every candidate field must carry `source_url`, `captured_at`, `source_type`, and `evidence_excerpt` or a direct page reference. Classify each value as `confirmed`, `reported`, `estimated`, or `unknown`. An unverified search snippet can generate a lead but cannot support a final recommendation. Preserve conflicting observations rather than averaging them away.

For lodging, normalize at minimum: total stay price, nightly price, taxes/fees, room name, bed/occupancy, air conditioning, actual beachfront/access distance, sea-view wording, cancellation, deposit, breakfast, and availability for the exact dates. For transport, normalize: door-to-door duration, bus/train/minivan leg, ferry leg, departure point, one-way cost, transfer risk, and whether the quoted fare includes the ferry.

Use `score = weighted_fit - uncertainty_penalty - contradiction_penalty` only after hard constraints have passed. Unknown critical fields should trigger a verification task or an explicit exclusion; do not silently treat unknown as satisfied.

## Stop conditions

Stop when the shortlist has enough candidates with comparable room/date/occupancy data, all hard constraints for the recommended option are evidenced, prices are within the configured freshness TTL, and remaining uncertainty is stated. If no candidate satisfies all hard constraints, return the nearest compromises and identify which constraint must be relaxed.

## Web-routing and recovery

Use search for discovery, Scrapling for accessible pages, Playwright/CDP for deterministic interactions, and Camoufox/local authenticated sessions for protected or cookie-bound pages. If a search API rate-limits, reduce concurrency and fall back to the search engine's browser UI or direct official/OTA pages; do not fabricate results from a partial response. When an OTA resets dates or guests, treat all displayed prices as invalid until the UI state is corrected and re-read. A page saying `2-minute walk` fails a strict "on the sand" requirement unless the user accepts that relaxation.

## Output contract

Present a compact decision table, then explain the top 2–4 options:

- exact price and what it includes;
- proof of beachfront/sea view/air conditioning;
- transport time and cost from the user's origin;
- confidence and capture time;
- trade-offs, unresolved risks, and source URLs;
- a clear recommendation conditional on the user's priorities.

Never auto-book. The final answer should distinguish a verified offer from a promising lead, especially when flexible dates prevent a live availability check.
