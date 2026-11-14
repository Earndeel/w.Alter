---
name: comparative-research
description: Use for constraint-verified multi-candidate comparisons.
---

# Comparative Research

For the multi-agent hotel-research workflow, see `references/agentic-hotel-research.md`. with Constraint Verification

## Trigger
The user asks for a ranked/sorted shortlist (destinations, products, tools, services) that must satisfy 3+ hard constraints — especially when one constraint is subtle or commonly misrepresented by listings.

## Methodology

### Phase 1: Candidate Discovery
- Broad exploratory search to identify 8–15 candidates
- Pre-filter by hard geographic/temporal/logical constraints
- Don't over-filter early — a candidate that's 80% compliant may turn out to be the best

### Phase 2: Independent Constraint Verification
For EACH candidate, verify EACH constraint from independent, purpose-specific sources. Never rely on a single aggregator for all constraints.

| Constraint Type | Best Source Types |
|----------------|-------------------|
| Transport cost/schedule | Booking aggregators (12go.asia, Rome2Rio, Busbud) |
| Accommodation price | OTA price grids + independent review sites |
| Features/quality | Independent review sites (Travelfish, expert blogs, Reddit) |
| Spatial claims ("on the beach") | Satellite view + review site photos + independent descriptions |
| Weather/seasonality | Dedicated weather/climate resources per region |

**Key pitfall**: Aggregator descriptions routinely overclaim. "Beachfront" on OTAs often means "within walking distance" or "has some rooms with sea view." Cross-reference spatial claims with satellite imagery and independent reviews that explicitly describe the access (road? promenade? stairs? direct sand?).

### Phase 3: Constraint Matrix
Build a table. Every candidate gets a row. Every constraint gets a column. Explicitly flag every violation.

```
| Candidate | Constraint A | Constraint B | Constraint C | Verdict |
|-----------|-------------|-------------|-------------|---------|
| Candidate 1 | ✅ OUI, 250 THB | ✅ OUI, 4 options | ✅ OUI | ⭐⭐⭐⭐⭐ |
| Candidate 2 | ✅ OUI | ⚠️ limité | ✅ OUI | ⭐⭐⭐⭐ |
| Candidate 3 | ✅ OUI | ❌ NON (reason) | ✅ OUI | ⭐⭐⭐ |
```

Use `✅ OUI` / `⚠️ PARTIEL` / `❌ NON` with a one-line reason for each flag. Never bury violations in prose — the comparison table IS the deliverable.

### Phase 4: Recommendation
- Top pick that satisfies ALL constraints
- Runner-up (e.g., closer but fewer options)
- "If constraint X is relaxed" fallback
- Never recommend a candidate that fails a hard constraint without explicitly calling out the tradeoff

## Output Rules
- Produce the full report in the user's requested language
- Keep URLs raw (not translated)
- Keep prices in local currency
- Keep proper nouns in original language
- Every price/claim must have a source URL

## Anti-Patterns
- Relying on a single OTA for spatial/factual claims — always cross-reference
- Assuming low season = bad weather — some regions are drier during monsoon
- Skipping weather verification — regional microclimates vary enormously
- Burying constraint violations in prose — use explicit flags in the matrix
- Presenting candidates that fail hard constraints as "options" without warning

## Reference Files
- `references/travel-sources-se-asia.md` — Thailand-specific transport/accommodation/weather sources, "on the sand" verification patterns, seasonal domain knowledge
- `references/dynamic-ota-verification.md` — rendered-browser sequences for exact dates, room-level evidence, hidden prices, and parallel OTA escalation

  ## Transport Comparisons (door-to-door)

  For comparing transport options between multiple destinations (bus/train/ferry/flight), use a **segment-based methodology** with **confidence-annotated prices**:

  ### Workflow
  1. **Phase 1 — Gather raw data** from multiple source types in parallel:
     - **Booking platforms** (12Go, Google Flights) → browser_navigate (JS-only)
     - **Transport guides** (Travelfish, Rome2Rio, local tourism sites) → Scrapling stealthy_fetch
     - **Web searches** (Brave) for blogs, schedules, operator sites — but watch for rate limits
  2. **Phase 2 — Extract structured data** using execute_code: compile prices, durations, operator names, frequencies, and last departures per route
  3. **Phase 3 — Calculate door-to-door** for each destination+mode by breaking into segments: origin→terminal→wait→transport→wait→transfer(ferry/taxi)→hotel. Use `references/thailand-transport-comparison.md` for Thailand-specific constants.
  4. **Phase 4 — Verify flights explicitly**: check if available, state whether cheaper/faster door-to-door or data inaccessible. The answer is often "route not operated" — default assumption without evidence is wrong.
  5. **Phase 5 — Build normalized table**: destination, mode, segments, duration, cost (single/return), confidence level, source URLs, bagage, conditions. Include raw sources table, methodology notes, and season caveat.

  ### Confidence system
  - ★★★ = Price shown on booking platform for exact date
  - ★★☆ = Reliable generic price from established guide
  - ★☆☆ = Estimate based on public knowledge, unverified for date
  - N/A = Route not operated or data inaccessible

  ### Critical Thailand pitfalls
  - **U-Tapao (UTP)**: Bangkok→UTP flights do NOT operate commercially (verified via Google Flights + airline sites). Never assume this route exists.
  - **12Go.asia**: JS-only SPA. Can be blocked (no DOM). Use date params in URL, fall back to generic route page + date picker.
  - **Google Flights**: Verify year in date picker (Aug 17 on a Monday = 2026). Airline direct search URLs often return 502.
  - **Bangkok Airways BKK→TDX (Trat)**: Only airline on this route, ~3 flights/day. Verify via Google Flights, not airline site.
  - **August = low season**: rain cancellations possible for ferries. Prices generally lower. Note this in the report.
