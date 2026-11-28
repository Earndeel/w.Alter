# Travel & Booking Research Sources (SE Asia / Thailand)

## Transport — live prices + schedules
| Source | Method | Notes |
|--------|--------|-------|
| 12go.asia | `browser_navigate` to route page | Live prices, operator ratings, duration. Snapshot extraction. |
| Rome2Rio | `browser_navigate` to route | Good discovery; prices are estimates not live. |
| MaratNomad.com | `browser_navigate` or `web_search` | Verified Thai train/bus schedules with fare ranges. |

## Accommodation — price + honest assessment
| Source | Method | Notes |
|--------|--------|-------|
| Travelfish.org | `web_search site:travelfish.org` | Best independent assessments. Describes beach access, AC, price. |
| Thailandee.com | `web_search` or `browser_navigate` | Budget lists with price bands ($-$$$$). |
| Agoda | `browser_navigate` with city+date+price params | Price filters work well. |
| Booking.com | `web_search` | Supplement to Agoda. |

## Weather / Seasonality
| Source | Method | Notes |
|--------|--------|-------|
| Travelfish weather | `web_search site:travelfish.org weather` | Monthly rainfall mm, per-region practical advice. |
| Thailandbeaches.org | `web_search` | Regional monthly summaries. |

## "On the sand" / "beachfront" verification cheat sheet
Aggregators routinely overclaim beachfront status. Cross-reference always.

**Red-flag phrases** (NOT on the sand):
- "across the road from the beach"
- "a short walk to the beach"
- "near the beach" / "beach nearby"
- "beach view" (view ≠ access)

**Green-flag phrases** (likely on the sand):
- "directly on the beach"
- "steps from the sand"
- "bungalows on the sand"
- "no road between resort and beach"

**Geography check**: If satellite view shows a road between hotel and beach, it's NOT on the sand regardless of what the listing says.

## Thai Gulf Coast domain knowledge
- **Upper Gulf** (Hua Hin, Cha-am, Pranburi, Pattaya): coastal road separates most hotels from beach. Budget beachfront = extremely rare.
- **Koh Samet**: national park island. Bungalows directly on sand are common on Ao Phai, Ao Hin Khok, Ao Wong Deuan. No coastal road.
- **Koh Larn** (near Pattaya): smaller supply but some beachfront on Samae/Nual beaches.
- **Koh Chang** (Trat): excellent beachfront bungalows BUT monsoon June–October (500mm+/month). Many places close Aug–Oct.
- **August microclimate**: Upper Gulf = surprisingly dry (brief afternoon showers). Andaman coast = monsoon. Lower east Gulf (Koh Chang) = heavy rain.

## Rate limit fallback
If `web_search` returns HTTP 429:
- Batch queries in `execute_code` with natural delays between calls
- Vary query phrasing between attempts
- Navigate directly to known aggregator URLs via `browser_navigate` (12go.asia, Rome2Rio)
- For accommodation, use Agoda/Booking URL patterns directly
