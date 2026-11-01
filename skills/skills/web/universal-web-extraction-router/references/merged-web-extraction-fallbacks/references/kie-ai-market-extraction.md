# Kie.ai Market Extraction — Reference

## Date
2026-06-26 (corrected)

## Problem
Extract model list from `https://kie.ai/market` and compare with API data. Browser tools (browser_navigate → browser_vision) lost session state repeatedly.

## Solution
Playwright headless screenshots (3 viewport positions: top/mid/bottom) + `vision_analyze` on saved PNGs. API data fetched via `urllib` from `/api/v1/playground/model-paths`.

## Corrected Data Points (post-verification)
- **API returns 95 model-paths** (not 176 — earlier count was stale/cached data)
- **UI shows ~30 distinct model brands** grouped by category (Text to Image, Text to Video, etc.)
- The apparent "delta" is explained by **variant paths**: e.g. `fal-ai/flux/dev`, `fal-ai/flux/schnell`, `fal-ai/flux/pro` = 3 API paths but 1 UI card ("Flux")
- Categories on UI: Text to Image, Text to Video, Image to Video, Audio/Music, 3D, AI Agents
- The "19 hidden models" claim was an artifact of counting raw API paths vs. grouped UI names — a normalization error

## Key Lesson
**Always normalize before comparing.** API model-paths include variant slugs (dev/schnell/pro, v1/v2) that collapse into single UI entries. Group by provider+base-name before computing deltas. And always show the raw data to the user before asserting conclusions.
