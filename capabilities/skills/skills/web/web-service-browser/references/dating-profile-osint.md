# Dating Profile OSINT & Analysis Patterns

## Analysis Workflow
1. **Identify the correct conversation** — verify timestamps by clicking into each, don't assume sidebar order
2. **Extract ALL profile text** — bio, prompts, basics (height, education, smoking, etc.), location, Spotify artists
3. **Screenshot EVERY profile photo** — scroll the right panel, screenshot at each position. NEVER use CDN URLs directly (see below).
4. **vision_analyze each screenshot** for:
   - Apparence physique, style vestimentaire
   - Lieu/décor (OSINT géographique — architecture, végétation, signalétique)
   - Langage corporel, expression faciale
   - Marques visibles (luxe, voitures, accessoires — Chanel, Porsche, Honda, etc.)
   - Signaux socio-économiques
   - Intention psychologique derrière la photo
   - Cohérence entre les photos (cheveux longs vs courts = époques différentes ?)
5. **Check social media** — if IG handle in bio, check profile (followers, posts, private/public, full name)
6. **Compile synthesis** — psychological profile, risk/interest assessment, conversation strategy

## CDN Image URLs — CRITICAL PITFALL
Dating apps (Bumble, Tinder, Hinge) use CDN image URLs that are **signed and session-bound**. Modifying parameters (especially `size=`) returns **wrong/different images**. This is NOT like modifying a generic image CDN URL.

**Tested case**: Changing `size=75x75` to `size=600x900` in Bumble CDN URLs returned photos of a completely different person (golf player instead of the actual woman).

**Rule**: Screenshots ONLY. Download CDN images at your own risk — always verify with vision_analyze that the content matches what you see in the screenshots.

## Instagram OSINT from Dating Profiles
- Many profiles include IG handle in bio (e.g. "IG : sunn.f")
- Even private profiles reveal: full name, post count, follower count, following count, bio, location
- Full name from IG can be used for broader OSINT (LinkedIn, Facebook, etc.)
- Follower count indicates social influence level (7K+ = micro-influencer territory)
- Post count + private profile = active user who curates access

## Psychological Photo Analysis Framework
For each profile photo, analyze:

1. **L'Archétype** — What persona is being projected?
   - La Rebelle (cigarette, bandana, regard provocateur)
   - La Voyageuse (plages, monuments, couchers de soleil)
   - La Chic (restaurants, robes, bijoux)
   - La Sportive (moto, gym, outdoor)
   - La Princesse (filtres, effets, poses étudiées)

2. **Le Contrôle** — How curated is the image?
   - Photo spontanée vs mise en scène professionnelle
   - Filtres/retouches visibles
   - Cohérence du style entre les photos

3. **Les Signaux** — What does the photo communicate?
   - Statut socio-économique (marques, lieux, activités)
   - Disponibilité émotionnelle (regard direct = ouverture, regard détourné = distance)
   - Recherche de validation (pose miroir, flexing luxe)
   - Authenticité (photos naturelles vs photos de studio)

4. **La Cohérence** — Do the photos tell a consistent story?
   - Style vestimentaire cohérent ou changeant ?
   - Même personne dans toutes les photos ?
   - Cheveux longs/courts = photos de différentes époques

## Conversation Analysis
- "Your move" = she messaged last, waiting for response
- Expiration timer = urgency signal — respond within window
- Bio tone analysis:
  - "No drama" = has been burned before, tests quickly
  - "No waste of time" = wants directness, rejects small talk
  - "Here for fun" = casual, not necessarily relationship-seeking
  - Emoji-heavy = Gen Z energy, keep it light
