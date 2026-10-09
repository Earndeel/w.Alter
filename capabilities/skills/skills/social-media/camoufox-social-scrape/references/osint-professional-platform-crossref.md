# OSINT Deep Dive: Professional Platform Cross-Reference

Once you identify a person's name + profession, exhaust ALL professional platforms before giving up. Each reveals different data.

## Platform Matrix

| Platform | What it reveals | URL discovery |
|----------|----------------|---------------|
| **Codeur.com** | Phone number (partially masked), career history, education, hourly rate, client reviews, verified LinkedIn | `codeur.com/-{username}` or Google `"Name Surname" site:codeur.com` |
| **Malt.fr** | Daily rate, skills, location, education, languages, client testimonials | Google `"Name Surname" site:malt.com` (direct URL construction 404s) |
| **LinkedIn** | Followers, job history, education, connections | Google `"Name Surname" LinkedIn` or link from website |
| **Tool Advisor** | Author bio, articles, preferred tools | `tool-advisor.fr/auteurs/{name-surname}` |
| **StarNgage** | Instagram analytics WITHOUT login: bio text, follower/following counts, engagement rate, post count, location, business category, website links. Works for public profiles. | Google `"@handle" site:starngage.com` or `starngage.com/chr/influencers/{handle}` |
| **Google Business** | Reviews, photos, location | Google Maps search |
| **Pages Jaunes** | Address, phone (landline only) | `pagesjaunes.fr` |
| **Societe.com / Pappers.fr** | Business registration, SIRET, directors | Search by name or company |

## StarNgage — Instagram Analytics Without Login

StarNgage is a free tool that indexes public Instagram profiles and provides analytics. It shows the full bio text (which often contains website links, business names, and location info), follower/following counts, engagement rate, and post count. This is invaluable when you can't log into Instagram to view a profile.

**Real example**: Searching for "Marika Palma Montpellier danse orientale" found the Instagram handle @marika.palma. StarNgage showed the bio: *"Bellydance Paris & Montpellier — Founder of @maisonsantal — Digital Marketing VA — Currently Bkk"*. The "@maisonsantal" reference linked the dancer persona to the known marketing freelancer Marika Moliner, confirming they were the same person.

**How to use**: Google `"@handle" site:starngage.com` or construct `https://starngage.com/chr/influencers/{handle}`. The page loads without authentication and shows the full Instagram bio text.

## Cross-Validation Technique

**Phone number matching** is the strongest identity signal when you have a WhatsApp number. Compare partially-masked numbers across platforms:
- Codeur.com shows "+33631…" → matches WhatsApp "+33 6 31 01 97 26" → CONFIRMED
- LinkedIn verification badge → account exists
- Malt.fr location matches known city → CONFIRMED

## Multiple Name Forms

People use different names across platforms. Search for ALL variants:
- **Real name vs nickname**: Marieke → Marika (Dutch formal → French informal)
- **Dating app name vs real name**: Elissa (Tinder) → Marika (WhatsApp, real name)
- **Stage name vs professional name**: Marika Palma (dancer) → Marika Moliner (freelancer)
- **Maiden name vs married name**
- **First name + last initial vs full name**
- **Cultural name variants**: Marieke (Dutch) = Marika (international)

If Tinder shows "Elissa" but WhatsApp shows "Marika", search web for BOTH — the real name usually yields better professional results.

## Cultural/Ethnic Name Signals

A non-French name (e.g., "Marieke" = Dutch) can explain:
- Trilingual ability (French + native language + English)
- Employment at companies from that country (Asiatides Import = Dutch import company)
- Specific cultural activities
- University location (Université Paris 8 has international students)

Use this to expand search queries and understand career history.

## Real Example: Marika Moliner (2026-05-22)

**Starting data**: First name "Marika" (WhatsApp), "Elissa" (Tinder), marketing/SEO, Montpellier + Bangkok, phone +33 6 31, photo (auburn curly hair)

**Search sequence that worked**:
1. Brave API: 10 queries → ZERO (too low-profile)
2. Bing Images "Marika marketing Montpellier": generic agencies, no match
3. Bing Images "Marika SEO Montpellier": generic, no match
4. Bing Images "Marika danse orientale Montpellier": WATERMARK "Marika Danse" found! Group photo with auburn-haired woman.
5. Google Images "Marika marketing SEO Montpellier" (via Scrapling bypass): **Digital Bliss** match! Red/auburn curly hair, marketing agency.
6. URL slug analysis: `digitalbliss.fr/a-propos-marieke-moliner` → full name **Marieke Moliner**
7. Codeur.com deep dive: phone +33631… (matches WhatsApp), career history, education, trilingual
8. Malt.fr profile: Bangkok + Montpellier, €350/jour, Veranex
9. LinkedIn: 590+ followers, Sorbonne Nouvelle
10. Tool Advisor: author page, preferred tools (Canva, Jira, HubSpot)
11. StarNgage @marika.palma: bio says "Founder of @maisonsantal" → confirms dancer = freelancer

**Result**: Complete dossier — name, DOB, phone, career history, education, certifications, skills, platforms, appearance, cultural background, dance persona.
