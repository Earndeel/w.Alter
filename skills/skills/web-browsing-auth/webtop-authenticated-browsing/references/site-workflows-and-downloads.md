## Download URL Capture

When a site uses S3/CDN downloads triggered by button clicks, intercept the URL via Playwright's `expect_download`:

```python
with page.expect_download(timeout=15000) as dl_info:
    page.click('button:has-text("Download")')
dl = dl_info.value
s3_url = dl.url  # Pre-signed S3 URL, valid for hours/days
# curl directly to VPS instead of saving through remote browser
subprocess.run(["curl", "-sL", "-o", f"/tmp/{dl.suggested_filename}", dl.url])
```

This avoids the 0-byte file issue when Playwright tries to save downloads from a remote CDP browser (download happens on the remote machine, not locally).

## Site-Specific Tricks

### Google Flow (labs.google/fx/tools/flow)
- Auth via Google cookies (filter `pw_cookies` where `"google" in c["domain"]`)
- Credits: click the profile button (has "PRO" text), a dialog shows `<N> Crédits Flow` as a link
- The credits link goes to `one.google.com/ai/activity?utm_source=flow&utm_medium=web&utm_campaign=flow_ai_credits_page`
- "Changer de forfait" and "Gérer l'abonnement" links also in profile dialog
- Projects listed below the hero banner as links with edit/delete buttons
- Navigation is French-localized (bouton "Nouveau projet", "Changer de forfait", etc.)
- Session key: `google-flow`
- Works on both host Camoufox and Camoufox-in-Webtop

### Google Flow (labs.google/fx/tools/flow)
- Auth via Google cookies (filter `pw_cookies` where `"google" in c["domain"]`)
- Credits: click the profile button (has "PRO" text), dialog shows `<N> Crédits Flow` as a link
- Profile dialog also has: "Changer de forfait", "Gérer l'abonnement", "Se déconnecter"
- Projects listed below hero banner as links with edit/delete buttons
- French-localized: "Nouveau projet", "Changer de forfait"
- Session key: `google-flow`

### Facebook People Search

```
https://www.facebook.com/search/people/?q=<query>
https://www.facebook.com/search/groups/?q=<query>
```

Results appear as `article` elements with `link "Profile photo of <Name>" [eN]` refs. Use regex `r'link "Profile photo of (.+?)"'` to extract names from snapshot.

### Instagram Search

Instagram's `/explore/search/?q=<query>` URL shows the Explore page with reels, NOT search results. To search users:

1. Navigate to `https://www.instagram.com/`
2. Click the Search icon (`link "Search"`)
3. Find the `textbox "Search input"` ref in the snapshot
4. Type the query → wait 3s → snapshot shows user results as `link "<username>'s profile picture <username> <display_name>"` refs

### LinkedIn Cookie Expiry

LinkedIn session cookies (`JSESSIONID`, `bscookie`) expire much faster than Facebook/Instagram. If the Camoufox snapshot shows the login page ("S'identifier"), the session is dead — no workaround without fresh credentials.

### Facebook Marketplace — Direct URL with Filters

Skip the UI search form entirely. Marketplace accepts filter params in the URL:

```
https://www.facebook.com/marketplace/bangkok/search/?query=pixel&maxPrice=4000
https://www.facebook.com/marketplace/bangkok/search/?query=pixel&minPrice=1000&maxPrice=5000
```

Available params: `query`, `maxPrice`, `minPrice`, `category_id`, `sortBy` (e.g., `creation_time_descend`, `price_ascend`, `price_descend`).

This is faster and more reliable than trying to interact with the search form (the combobox "Search Marketplace" has no `[eN]` ref in Camoufox snapshots).
