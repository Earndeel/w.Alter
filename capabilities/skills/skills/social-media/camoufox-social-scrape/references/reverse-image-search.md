# Reverse Image Search Workflow

When you have photos of the target (from Tinder, WhatsApp, etc.), reverse image search can find their other social media profiles.

## Google Lens (BLOCKED — even non-headless + residential IP)
Google detects automated browsing via TLS fingerprint and JS properties, NOT just IP or headless flag. Even running Camoufox in non-headless mode on Webtop Xvfb (visible via Selkies) with a residential IP (Mac Tailscale exit node, Thai ISP) returns **403 Forbidden** on Google Lens. Google homepage works fine — only Lens/advanced search has strict anti-bot. **Never attempt Google Lens from automation.**

## Private Photos (Tinder, WhatsApp) — NOT INDEXED
Photos from dating apps (Tinder's `images-ssl.gotinder.com`) and messaging apps are private CDN links — they are NOT indexed by any search engine (Google, Yandex, TinEye, Baidu). Reverse image search will find visually similar photos of OTHER people but never the exact private photo. For Tinder matches, use the Tinder API to get photos, then analyze them with `vision_analyze` for location/lifestyle clues. Don't waste time on reverse image search for private photos.

## Yandex Images (WORKS from servers)
Yandex is the best reverse image search for server-based automation. Less aggressive anti-bot.

### URL-based search (no upload needed):
```python
import urllib.parse
image_url = "https://..."
encoded = urllib.parse.quote(image_url, safe='')
yandex_url = f"https://yandex.com/images/search?rpt=imageview&url={encoded}"
```

### Workflow:
1. Navigate to the Yandex URL with Camoufox
2. Yandex shows: "Image appears to contain" (auto-detected labels), "Similar images", and "Sites" tabs
3. Check **"Sites" tab** first — this shows WHERE the exact image appears online (social profiles, articles)
4. Check **"Similar images"** — may find the same person in different photos
5. The "Image appears to contain" labels help refine further searches

### Pitfalls:
- Yandex results are often NSFW/leak sites for attractive women — filter mentally
- The "Sites" tab is the most valuable for OSINT (finds the actual profile hosting the photo)
- Yandex auto-detects language based on IP — may show Thai/Turkish/etc UI elements
- If one photo yields nothing, try another (profile photos often work better than landscape/travel shots)

## TinEye
Direct URL search: `https://tineye.com/search?url={encoded_url}&sort=size&order=desc`
Works from servers but has a smaller index than Yandex. Best for finding exact copies of professional photos.

## PimEyes / Face Recognition
Paid services that do face recognition (not just image matching). Not available via API — requires browser + subscription. Consider as last resort for high-value targets.

## Photo OSINT Analysis Template
For each photo, use `vision_analyze` to extract:
1. **Physical appearance**: hair color (natural vs dyed), style, skin tone, age estimate
2. **Location clues**: landmarks, architecture, vegetation, signs in local language
3. **Setting**: apartment style (luxury vs basic), hotel brand (Versace, Marriott), resort type
4. **Clothing/jewelry**: brands, style (casual, formal, dance costume), accessories
5. **Activity**: tourist, working, performing, exercising
6. **Background text**: any visible signs, logos, brand names, license plates
7. **Time of day**: lighting, shadows (helps narrow location by latitude)
