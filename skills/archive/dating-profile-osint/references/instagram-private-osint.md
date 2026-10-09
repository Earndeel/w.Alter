# Instagram OSINT — Private Profile Data

Even on PRIVATE profiles, the public web interface reveals significant data without login.

## What's Visible on Private Profiles (No Login Required)

| Data | Available | Example |
|------|-----------|---------|
| Username | ✅ | sunn.f |
| Full name | ✅ | Arisara M. Sunphie |
| Post count | ✅ | 543 posts |
| Follower count | ✅ | 7,816 followers |
| Following count | ✅ | 1,561 following |
| Bio text | ✅ | "Bangkok \| Thailand 🫶🏻" |
| Profile pic | ✅ | Low-res circular |
| Private status | ✅ | "This profile is private" |

## What's NOT Visible (Login Required)

- Photo grid
- Story highlights
- Tagged photos
- Reels
- Comments
- Following/followers list

## Extraction via Camoufox

```python
import http.client, json, time

# Navigate to profile
conn = http.client.HTTPConnection('localhost', 9378, timeout=20)
body = json.dumps({'userId': 'walter', 'sessionKey': 'ig-target', 
                   'url': f'https://www.instagram.com/{handle}/'})
conn.request('POST', '/tabs', body, {'Content-Type': 'application/json'})
tab_id = json.loads(conn.getresponse().read().decode())['tabId']

# Wait for load, then close signup dialog if present
time.sleep(8)
# Click close button on signup dialog
conn.request('POST', f'/tabs/{tab_id}/click', 
    json.dumps({'userId': 'walter', 'sessionKey': 'ig-target', 'ref': 'e1'}),
    {'Content-Type': 'application/json'})

# Snapshot — extract data
conn.request('GET', f'/tabs/{tab_id}/snapshot?userId=walter&sessionKey=ig-target')
snapshot = json.loads(conn.getresponse().read().decode())['snapshot']

# Parse: name, posts, followers, following, bio all appear in the snapshot text
```

## Public Profile Deep Extraction

For public profiles, login via cookies enables full access:

```python
# Inject Instagram cookies from Mac Brave
# Then navigate to profile
# Extract: photo grid URLs, highlights, tagged photos, reels
```

### Photo Grid Analysis
- **Aesthetic consistency**: Same filter/color palette = curated brand
- **Post frequency**: Daily = influencer, monthly = casual
- **Content mix**: selfies vs travel vs food vs friends (personality signals)
- **Engagement**: visible likes/comments on public posts

### Story Highlights (Public Profiles)
- Categories reveal priorities: Travel, Food, Fitness, Friends, Work
- Highlight covers show aesthetic level
- Number of highlights = investment in self-presentation

## Cross-Platform Correlation

From a dating profile, you can often find:
1. **Instagram handle** → full name, location, lifestyle
2. **Spotify artists** → personality, cultural taste
3. **Full name** → LinkedIn (professional verification), Facebook (social circle)
4. **Location + first name** → Thai directory searches, university alumni

## Follower/Following Ratio Analysis

| Ratio | Signal |
|-------|--------|
| Followers >> Following | Influencer/public figure, selective |
| Followers ≈ Following | Normal social butterfly |
| Followers << Following | Follows back everyone, may be building audience |
| 1K-5K followers (private) | Popular in social circle, not influencer |
| 5K-20K followers (private) | Micro-influencer or very social |
| 20K+ followers (private) | Likely public figure or semi-celebrity |

## Pitfalls

1. **Don't assume "private" = hiding something**: Many Thai women keep profiles private to control who sees their photos — cultural norm, not red flag.
2. **Follower count varies by culture**: 7K followers for a Thai woman in Bangkok = normal social life. Same number in rural US = unusually high.
3. **The "M." in names**: Thai middle names are common. "Arisara M. Sunphie" — M. could be a middle name, maiden name, or family name variant.
4. **Don't send follow requests** from user's account without explicit permission — this is visible and can be awkward.
