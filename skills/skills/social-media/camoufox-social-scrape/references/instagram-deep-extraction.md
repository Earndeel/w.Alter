# Instagram Deep Extraction Without Login

When you find an Instagram handle but cannot view the profile (login wall), you can still extract substantial data from three public sources.

## Source 1: Google Search (Cached Posts)

Search: `site:instagram.com "{handle}"`

Returns:
- Post captions with dates (e.g., "marika.palma on May 11, 2023: 'La danse orientale...'")
- Engagement metrics (likes, comments)
- Hashtags used
- Who TAGS them in posts (other accounts mentioning the handle)
- Reel/video titles

Search: `"{handle}" site:instagram.com -site:instagram.com` (exclude IG direct)

Returns:
- Third-party mentions (blog posts, analytics sites, community pages)
- Cross-references from other platforms

## Source 2: StarNgage Analytics

URL: `https://starngage.com/chr/influencers/{handle}`

Returns:
- Full bio text (including links, emojis, location)
- Follower/following counts
- Post count
- Engagement rate
- Business category
- Location tags
- Sometimes website links

This was the breakthrough for confirming Marika Palma = Marika Moliner: StarNgage showed "Founder of @maisonsantal" in the bio, linking the dance persona to the known e-shop.

## Source 3: Google Images

Search: `"{handle}" site:instagram.com` on Google Images

Returns:
- Actual post thumbnails (visual content)
- Profile picture
- Grid layout hints

Combine with vision_analyze to examine each image.

## Source 4: Screenshot via Scrapling (Login Wall)

Even with the login wall, the profile page shows:
- Bio text (emojis, location, description)
- Story highlight names
- Top 6 grid thumbnails
- Follower/following/post counts
- Profile photo

```python
mcp_scrapling_open_session(session_type="stealthy", solve_cloudflare=True)
mcp_scrapling_screenshot(session_id=..., url="https://www.instagram.com/{handle}/", wait=5000)
# vision_analyze the screenshot for all visible data
```

## Combined Extraction Pattern

1. Screenshot the profile → get bio, highlights, grid preview, stats
2. Google search → get recent post captions, engagement, tagged-by
3. StarNgage → get full bio, engagement rate, business category
4. Google Images → get visual content of posts
5. Cross-reference all three to build a complete profile

## Example: @marika.palma

| Data Point | Source | Value |
|-----------|--------|-------|
| Bio | Screenshot + StarNgage | Bellydance Currently Bkk Worked in France Italy Lebanon Egypt Bahrain |
| Stats | Screenshot | 303 posts, 3757 followers, 347 following |
| Story highlights | Screenshot | Classes, Bahrain, Al Musiqar |
| Recent posts | Google search | "New weekly belly dance classes in Bangkok", "Dance intensive in China" |
| Community | Google search | Tagged by @bellysister, @gift_bellysister, @le_dansebkk |
| Identity link | StarNgage | "Founder of @maisonsantal" = known e-shop |
