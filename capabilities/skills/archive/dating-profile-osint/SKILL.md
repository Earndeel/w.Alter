---
name: dating-profile-osint
description: "Analyze dating app profiles (Bumble, Tinder, Hinge) for OSINT and psychology signals — photo analysis, bio parsing, Instagram cross-reference, behavioral profiling."
version: 1.0.0
author: W.Alter
triggers:
  - analyse profil
  - dating profile
  - osint profil
  - psychologie photo
  - bumble profile
  - tinder profile
  - analyze photos
metadata:
  hermes:
    tags: [osint, dating, bumble, psychology, photos, instagram, research]
    related_skills: [web-service-browser, webtop-authenticated-browsing, camoufox-social-scrape]
---

# Dating Profile OSINT & Psychology Analysis

Analyze dating app profiles to extract OSINT data and psychological signals from photos, bio text, prompts, and linked social accounts.

## When to Use

- User asks to analyze a dating profile (Bumble, Tinder, Hinge)
- User wants to understand someone's personality from their photos
- User asks for advice on a match or conversation
- OSINT on a person via their dating profile

## Pipeline

```
1. Open dating app (cookies via web-service-browser skill)
2. Navigate to target profile
3. Extract: photos, bio, prompts, basics, linked accounts
4. Download full-res photos via CDN URLs
5. Analyze each photo with vision_analyze (OSINT + psychology)
6. Cross-reference Instagram/social if available
7. Synthesize: psychological profile, compatibility signals, conversation strategy
```

## Step 1: Extract Profile Data

### Bumble Profile Elements
- **Photos**: carousel, click through each. CDN: `us1.ecdn2.bumbcdn.com/pNNN/hidden?euri=...&size=453x1536` for full-res
- **Bio/About**: text section below photos
- **Profile Prompts**: questions + answers (e.g., "My healthy obsession is...")
- **Basics**: height, exercise, education, drinking, smoking, looking for, kids, star sign, politics, religion, gender
- **Location**: city + distance
- **Spotify**: top artists (strong personality signal)
- **Instagram**: handle (cross-reference for deeper OSINT)
- **Conversation**: message history for tone analysis

### Photo Extraction (Bumble)
```python
# Get all photo URLs from the profile page
photo_urls = page.evaluate("""() => {
    const imgs = document.querySelectorAll('img');
    return Array.from(imgs)
        .map(i => i.src)
        .filter(s => s.includes('ecdn2') && s.includes('size=453x1536'));
}""")

# Download each photo (Referer header required)
import subprocess
for i, url in enumerate(photo_urls):
    subprocess.run([
        "curl", "-sL", "-o", f"/tmp/profile-photo-{i}.jpg",
        "-H", "Referer: https://bumble.com/", url
    ], timeout=15)
```

**Pitfall**: Bumble CDN returns 403 without `Referer: https://bumble.com/` header.

## Step 2: Photo Analysis Framework

For EACH photo, analyze with `vision_analyze` covering these axes:

### OSINT Signals
- **Location clues**: architecture, vegetation, signage, language on signs, power lines (aerial = SE Asia), vehicle plates
- **Brands/marques**: clothing labels, car logos, equipment brands, bags, shoes
- **Timestamps**: daylight/night, seasonal clothing, event decorations (NYE, Songkran, etc.)
- **Text visible**: street names, shop names, phone numbers, social handles on shirts
- **Technology**: phone model, camera quality, editing style (VSCO, Lightroom, etc.)
- **People**: who else is in the photo (friends, family, children, ex?)

### Psychology Signals
- **Expression**: genuine smile (Duchenne) vs posed, neutral, provocative, shy
- **Eye contact**: direct (confidence/openness), averted (shyness/coyness), upward (aspirational)
- **Posture**: open (arms uncrossed, body forward = engagement), closed (defensive), leaning (interest)
- **Pose intention**: mannequin pose (image-conscious), candid (authenticity-seeking), activity (lifestyle signaling)
- **Photo quality**: professional studio (invested in image), selfie (casual), friend-taken (social), mirror selfie (self-sufficient)
- **Editing**: filters (nostalgia/warmth), beauty filters (insecurity or image control), no filter (authenticity)

### Socio-Economic Signals
- **Clothing quality**: fast fashion vs designer vs vintage
- **Accessories**: watches, jewelry, bags (price indicators)
- **Environment**: restaurant tier, car interior, home decor, travel destinations
- **Activities**: sports (equipment cost), travel (frequency/destinations), dining (venues)

## Step 3: Instagram Cross-Reference

Even on PRIVATE profiles, Instagram reveals:
- **Full name** (displayed on profile)
- **Post count** (activity level)
- **Follower/following ratio** (influence/popularity)
- **Bio text** (interests, location, contact)
- **Profile pic** (different from dating app)

```python
# Open Instagram profile in Camoufox
conn.request('POST', '/tabs', json.dumps({
    'userId': 'walter', 'sessionKey': 'ig-target',
    'url': f'https://www.instagram.com/{handle}/'
}), {'Content-Type': 'application/json'})

# After loading, get snapshot — even private profiles show:
# - Full name, posts, followers, following
# - Bio text
# - "This profile is private" confirmation
```

### Public profiles reveal additionally:
- Photo grid (aesthetic consistency, lifestyle patterns)
- Story highlights (priorities, travel, food, fitness)
- tagged photos (social circle, activities)
- Reels (personality, humor, interests)

## Step 4: Synthesis Template

```
━━━ [NAME] — Analyse complète ━━━

▸ NOM COMPLET : [from Instagram]
▸ INSTAGRAM : @[handle] ([PRIVÉ/PUBLIC])
▸ [N] posts | [N] followers | [N] following
▸ [Age] | [Job] | [Height] | [Religion] | [Star sign]

━━━ ANALYSE DES PHOTOS ━━━

PHOTO N — [Title] (one per photo)
▸ [Clothing/style description]
▸ [Location/environment]
▸ [Expression/body language]
▸ Signal: [what this photo communicates intentionally]
▸ OSINT: [any concrete intel extracted]

━━━ SYNTHÈSE PSYCHOLOGIQUE ━━━

▸ [Dominant personality archetype across photos]
▸ [Authenticity level: how curated vs real]
▸ [Social proof signals: followers, photo quality, lifestyle]
▸ [Compatibility indicators]
▸ [Red/green flags]

━━━ PROFIL RISQUE / INTÉRÊT ━━━

▸ Intérêt: [HIGH/MEDIUM/LOW — based on their engagement signals]
▸ Manipulation: [LOW/MEDIUM/HIGH — game-playing signals]
▸ Authenticité: [how genuine vs performative]
▸ [Conversation strategy recommendation]
```

## Conversation Response Drafting

When Monsieur asks for response suggestions to dating conversations, follow this workflow AFTER extracting profile data:

### Step 1: Identify Active Conversations
- "Your move" = she messaged last, waiting for response (PRIORITY)
- Click into each "Your move" conversation to verify timestamps
- Do NOT assume sidebar order = most recent incoming message

### Step 2: Extract Full Context per Conversation
For each active conversation, gather:
- **Full message history** (direction + text for last 10-20 messages)
- **Profile details** (age, bio, basics, photos via screenshots)
- **Expiration status** (how much time left to respond)
- **Her energy level** (from messages: flirty, casual, serious, boring)

### Step 3: Analyze Communication Vibe via Screenshots
Use `vision_analyze` on conversation screenshots to assess:
- Her messaging style (emoji-heavy, short, long, provocative)
- Photo vibe (party girl, serious, adventurous, etc.)
- Bio signals (relationship goals, lifestyle markers)

### Step 4: Draft Responses (3 Options per Conversation)
Each set should include:
1. **Recommended** — best fit for her energy + his style
2. **Alternative tone** — different angle (more playful, more direct, etc.)
3. **Safe/short** — minimal risk fallback

### Response Style Rules (Monsieur's preference)
- **3 propositions systématiques** pour chaque réponse
- **Langue de la conversation** (si elle écrit en anglais → anglais)
- **Style** : sexy, drôle, provoquant, mais pertinent (profil + contexte)
- **Pas orienté "rencontre physique" directe** — teasing, pas pression
- **Courts** — max 2 parties courtes
- **Pas toujours d'emoji** — varier, parfois aucun
- **Jamais de répétition** entre les 3 options (structures et mots différents)
- **Timestamps** : TOUJOURS recalculer en UTC+7 (Bangkok), jamais UTC brut
- NOT: "Hey! Would you like to grab a drink this week?" (too direct/transactional)
- NOT: every message ending with 😏 (don't overuse emojis)

### Energy Matching Matrix
| Her Energy | Your Response Energy | Example Pattern |
|-----------|---------------------|----------------|
| Very flirty/provocative | Bold + teasing | "Careful, I might take you up on that 😏" |
| Casual/curious | Warm + playful | "Better now 😏 What about you — what's keeping you busy?" |
| Serious/bio-focused | Genuine + curious | "A nurse AND a boat person? What's the story there?" |
| Boring/low effort ("How are you") | Relance with open question | "Still surviving Bangkok 😄 What about you — got any fun plans?" |

### Step 5: Prioritize
Rank conversations by:
1. **Response urgency** (expiration timer)
2. **Her energy level** (higher = more likely to convert)
3. **Conversation potential** (shared interests, profile quality)

### Output Format (for Telegram)
```
━━━ VOS N CONVERSATIONS EN ATTENTE ━━━

▸ NOM (age, details clés)
▸ Bio: "excerpt"
▸ Dernier échange: ← "her last message"

3 options de réponse :
1. **Type :** "réponse"
2. **Type :** "réponse"
3. **Type :** "réponse"
```

**See** `references/dating-response-style.md` for detailed message crafting guidelines and examples.

**Bulk extraction script**: `scripts/bumble-bulk-extract.py` — extracts all "Your move" conversations with full message history, profile data, and screenshots in one run. Copy to webtop and execute.

## Message Style Rules (Monsieur's preference)

- **3 propositions systématiques** pour chaque réponse à proposer
- **Dans la langue de la conversation** (si elle écrit en anglais → anglais)
- **Style** : sexy, drôle, provoquant, mais toujours pertinent par rapport au profil et au contexte
- **Pas orienté "rencontre physique" directe** — teasing, pas pression
- **Courts** — max 2 parties courtes, pas un paragraphe
- **Pas toujours d'emoji** — varier, parfois aucun
- **Jamais de répétition** entre les 3 propositions (ni de structures identiques, ni de mots-clés recyclés)
- **Timestamps** : TOUJOURS recalculer en fuseau du user (Bangkok UTC+7), jamais UTC brut

## Common Archetypes (photo patterns)

| Archetype | Photo Signals | Psychology |
|-----------|--------------|------------|
| **The Curator** | Every photo pro-quality, consistent aesthetic, color palette | High image control, values appearance, may be influencer |
| **The Adventurer** | Travel shots, outdoor activities, exotic locations | Values experiences, restlessness, may be avoidant |
| **The Socialite** | Group photos, events, nightlife, brand-heavy | Extroverted, validation-seeking, wide social circle |
| **The Minimalist** | Few photos, simple backgrounds, natural lighting | Confident, doesn't need validation, may be selective |
| **The Rebel** | Dark aesthetics, provocative poses, unconventional style | Independent, tests boundaries, may have trust issues |
| **The Nurturer** | Family photos, pet photos, cooking, cozy environments | Values connection, may want commitment quickly |
| **The Chameleon** | Every photo different style/persona | Adaptive, experimental, may lack stable identity |

## Pitfalls

1. **Don't confuse photo aesthetic with personality**: Someone with all pro photos may just be photogenic or have a photographer friend, not necessarily narcissistic.
2. **Cultural context matters**: Thai women often post filtered photos — this is cultural norm, not insecurity. Same for posing with luxury items.
3. **Instagram follower count ≠ relationship material**: 7K followers on a private Thai account = normal social butterfly, not influencer red flag.
4. **Children in photos**: Usually nieces/nephews in Thai culture. Check "want kids" field before assuming parenthood.
5. **The "ladyboy question" filter**: In Thailand, many women preemptively address this in their bio. It's defensive, not a red flag — they deal with intrusive questions constantly.
6. **Don't over-interpret single photos**: Look for PATTERNS across 4-6 photos. One provocative photo doesn't make someone a "rebel" archetype.
7. **Spotify artists are strong personality signals**: More reliable than bio text because they're passive data, not curated self-presentation.
8. **Timestamps MUST be converted to user's timezone**: Bumble shows relative timestamps ("10 hours ago", "3 hours ago"). These are relative to NOW in the browser's timezone (UTC for server). Always convert: `timestamp_utc + user_offset = local_time`. For Bangkok (UTC+7), a message "3 hours ago" at 06:48 UTC was sent at 10:48 Bangkok time, NOT 03:48. Getting this wrong leads to incorrect "drunk at 3am" narratives when the person actually sent it at a reasonable hour. This caused a major error in a 2026-06-03 session.
9. **Conversation corpus must be PROVEN complete before concluding an info is absent**: the Beeper API returns max 20 messages per page regardless of `limit`, and `beforeSortKey=` is silently ignored (same page loops forever) — only `cursor=` + `oldestCursor` descends. A one-call "delta" missed 43 messages including a name reveal on 2026-08-22. See `references/beeper-sync-and-extraction-lessons.md`.
10. **Extract profiles BY DIMENSION, not narratively**: age/occupation/names/routine/secrets can sit in the corpus unscanned after a narrative-only pass — this drew two explicit user corrections in one session. Run the full dimension grid (age, job, family, origin, routine, fears, vices, possessions, exes, secrets, money, languages, names incl. CJK characters), each claim backed by quote + message_id. Same reference file for the full checklist and the claims/evidence SQL pitfalls.
