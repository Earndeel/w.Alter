# Thailand Transport Door-to-Door Comparison — Sources & Methodology

## Tool Stack (by priority)

| Priority | Tool | Use Case | Pitfalls |
|----------|------|----------|----------|
| 1 | **browser_navigate + browser_vision** | 12Go.asia, Google Flights, airline sites (JS-only) | 12Go sometimes blocks; try date params in URL |
| 2 | **Scrapling stealthy_fetch** | Travelfish.org, blog guides (HTML, no JS required) | MCP may go down; backfill with browser |
| 3 | **web_search (Brave)** | Initial discovery, blog guides, aggregator references | **Rate-limit 429 is common** — use browser/Scrapling as fallback |
| 4 | **execute_code (compile phase)** | Combine all sources, calculate segments, build tables | Run only after raw data collected |

## Key Data Sources (Thailand Transport)

### Aggregators (primary — price verification)
- **12Go.asia** — `https://12go.asia/en/travel/{origin}/{destination}?date=YYYY-MM-DD`
  - JS-only SPA; use browser_navigate, never curl
  - Shows: combos (bus+ferry, van+ferry, taxi), prices, durations
  - For blocked dates, navigate to generic route page and use date picker
  - **Confidence: ★★★** (prices for exact date, includes taxes)

- **Google Flights** — `https://www.google.com/travel/flights?q=Flights+from+{origin}+to+{dest}+on+{date}+return+{date}`
  - Works with browser_navigate + browser_vision
  - **Confidence: ★★★** (prices for exact dates, but may differ from airline site ±10%)
  - Check that date picker shows correct year (Aug 17 on a Monday = 2026)

### Guide sites (secondary — schedules, operators, price ranges)
- **Travelfish.org** — `https://www.travelfish.org/transport/thailand/{region}/{province}/{pier}/all`
  - Static HTML, works with Scrapling stealthy_fetch
  - Most comprehensive English-language transport guides for SE Asia
  - **Confidence: ★★☆** (reliable generic data, not date-specific)

- **SiamTickets.com** — bus schedules and combo tickets
  - Bus Ekkamai→Ban Phe: ~THB 210-251
  - **Confidence: ★★☆**

- **KohLarn.com / PattayaCityTour.com** — ferry Pattaya→Koh Larn
  - **Confidence: ★★☆**

### Airline sites (direct booking — often JS-blocked)
- **Bangkok Airways** — BKK→TDX (Trat) for Koh Chang, BKK→UTP (rarely operated)
  - Direct URL search often returns 502; use Google Flights instead
- **AirAsia** — DMK→UTP (not operated), DMK→various domestic
  - Search form JS-only; browser_navigate then visual inspection
- **Nok Air, Thai Lion Air** — similar; DMK→UTP not operated

## Rate-Limit Fallback Pattern

When `web_search` returns HTTP 429 (Brave Search rate-limited):

1. **Pause** web_search calls for ~30 seconds
2. **Pivot immediately** to browser_navigate for key pages (12Go, Google Flights)
3. **Use Scrapling** stealthy_fetch for static HTML guides (Travelfish, blogs)
4. **Resume** web_search with narrower queries after rate-limit window clears
5. **Never** retry the same failing query in a loop — try a different tool or query

## Segment-Based Door-to-Door Calculation

For each destination and transport mode, calculate every leg:

```
Total = origin_city → terminal_1 (transit) + wait_1 + 
        terminal_1 → terminal_2 (main transport) + wait_2 +
        terminal_2 → pier/station (local transfer) + wait_3 +
        pier/station → island/beach (ferry if applicable) +
        arrival_pier → hotel (final transfer)
```

### Default wait times (Thailand)
- Bus terminal: 15-30 min before departure
- Flight check-in: 1h-1h30 domestic
- Ferry connection: 15-45 min (unless combo ticket with guaranteed connection)
- Airport transfer to pier: 30 min (Trat), 45 min (U-Tapao)

## Thailand-Specific Transport Constants

### Bangkok departure points
| Terminal | Destinations | Access |
|----------|-------------|--------|
| Ekkamai (Eastern) | Pattaya, Rayong, Ban Phe, Trat | BTS Ekkamai |
| Mo Chit (Northern) | Trat, Nakhon Ratchasima | BTS Mo Chit / MRT |
| Victory Monument | Minivans to Pattaya, Rayong, Hua Hin | BTS Victory Monument |
| Khao San Road | Minivans to Koh Chang, Koh Samet | Tourist area |
| Hua Lamphong / Bang Sue | Trains to Hua Hin, Surat Thani | MRT |

### Bus durations from Bangkok
| Destination | Duration | Price range |
|------------|----------|-------------|
| Pattaya | 2h-2h30 | THB 130-150 |
| Rayong | 2h30-3h | THB 210-250 |
| Ban Phe (Koh Samet) | 3h-3h30 | THB 200-300 |
| Trat (Koh Chang) | 5h-6h | THB 300-500 |
| Hua Hin | 3h-4h | THB 200-300 |

### Ferry routes
| Route | Duration | Price (slow boat) | Price (speedboat) | Frequency | Last return |
|-------|----------|-------------------|-------------------|-----------|-------------|
| Ban Phe → Koh Samet | 30-45 min | THB 70-120 | THB 200-400 | ~hourly 6:00-17:00 | ~17:00 |
| Laem Ngop / Ao Thammachat → Koh Chang | 30-45 min | THB 80-120 | — | ~hourly 6:30-18:30 | ~18:30 |
| Bali Hai Pier → Koh Larn | 30-45 min | THB 30-50 | — | ~hourly 7:00-18:00 | 18:00 ⚠ |

### Flight routes (Thailand domestic — beach destinations)
| Route | Airline | Duration | Typical AR price | Status (2026) |
|-------|---------|----------|-----------------|---------------|
| BKK→TDX (Trat) | Bangkok Airways | 1h00 | THB 4,000-5,500 | ✅ Operated (~3/day) |
| BKK→UTP (U-Tapao) | Bangkok Airways | 45 min | THB 2,500-4,000 | ❌ **Not operated** — verified Aug 2026 |
| DMK→UTP (U-Tapao) | AirAsia, Nok Air, Thai Lion | — | — | ❌ **Not operated** — verified Aug 2026 |

## Confidence Annotation System

Use these standard levels in all transport comparison tables:

| Level | Meaning | Example |
|-------|---------|---------|
| ★★★ | Price displayed on booking platform for the exact date | "12Go combo THB 402 for 17/08/2026" |
| ★★☆ | Reliable generic price from established transport guide | "Travelfish: bus Ekkamai→Ban Phe ~THB 200-250" |
| ★☆☆ | Estimate based on public knowledge, not verified for date | "Minivan Victory Monument→Rayong ~THB 250-350" |
| N/A | Data inaccessible or route not operated | "Flight BKK→UTP: no commercial service" |

## Output Format Standard

For transport comparison deliverables, always include these sections:
1. **Normalized comparison table** — destination, mode, segments, duration, cost, confidence, sources
2. **Explicit flight vs. road answer** — is flight cheaper? faster? or data inaccessible?
3. **Raw sources table** — source name, URL, date consulted, data extracted
4. **Methodology notes** — tools used, limitations encountered, margin of uncertainty
5. **Season note** — August = low/green season in Thailand (lower prices, possible rain cancellations)

## Common Pitfalls

1. **12Go date parameter works but content may be blocked** — If 12Go returns no DOM elements, the page JS was blocked (anti-bot). Try without date param and use the date picker.
2. **Google Flights may show wrong year** — Verify that the date picker shows 2026, not 2025 or 2027. August 17 is a Monday in 2026 — use this as a cross-check.
3. **Airline direct URLs often 502** — Don't waste time constructing URL parameters for airline search forms. Use Google Flights as the primary flight price source.
4. **Scrapling MCP may go down** — The MCP server is not always available. Collect data early and backfill with browser if it fails mid-session.
5. **U-Tapao (UTP) is a trap** — Despite being geographically close to Rayong/Pattaya, commercial flights BKK/DMK→UTP do NOT operate. Always verify rather than assuming.
6. **Never invent ferry frequencies or prices** — If a source doesn't specify a frequency, say "not specified" rather than guessing "every 30 minutes."
