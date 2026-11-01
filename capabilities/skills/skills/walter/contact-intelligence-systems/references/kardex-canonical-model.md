# Kardex Canonical Model — Deep Relationship Extraction Taxonomy

Kardex should model years of relationships as evidence-backed temporal dossiers, not one-shot summaries.

## Core Principle

Every extracted detail must be classified as:

- `explicit`: directly stated
- `inferred`: strongly implied by repeated behavior
- `speculative`: weak hypothesis, never treated as fact

Every claim needs evidence: source, message/media ID, timestamp, speaker, quote, confidence, extraction method, and counter-evidence when relevant.

## Identity Layer

Extract and separate:

- real names, first names, family names
- platform display names
- handles per platform
- phone numbers and emails
- nationalities, languages, age range, occupation
- stable aliases
- terms of address (`babe`, `darling`, `miss`)
- sexual/roleplay terms (`daddy`, `sir`) — never aliases by default
- joke identities (`56 years old Indian man`) — never aliases
- relationship labels: date, friend, ex, client, family, professional

## Social Graph

Track people around the contact:

- family members
- exes
- dates or romantic ambiguity
- friends, colleagues, roommates
- pets
- rivals / jealousy triggers
- people who influence decisions
- recurring people in stories/media

Store relation type, confidence, evidence, and impact on Monsieur’s relationship with the contact.

## Location and Movement

Extract:

- home city/country
- current location
- hotels / neighborhoods / venues
- travel arrivals/departures
- trip duration
- frequent locations
- emotionally significant places
- moving intentions
- timezone and availability windows

Do not create an event from merely mentioning a city. Create an event only for actual movement, plan, stay, or significance.

## Relationship Timeline

Important event types:

- first contact
- first media exchange
- first meeting/date
- physical intimacy
- emotional disclosure
- conflict and repair
- jealousy moment
- boundary set
- travel to see each other
- opportunity missed
- silence gap and reconnection
- pet/health/family/work life events
- relationship shift
- plan made/cancelled

Events should be clustered into episodes, deduplicated, ranked by importance, and linked to evidence.

## Conversation Episodes

Segment long histories by time gap and topic shift. For each episode extract:

- factual summary
- emotional summary
- key topics
- relationship impact
- tone: warm, cold, conflict, sexual, tender, sad, playful
- important quotes
- facts extracted
- open loops
- importance score

Episode summaries become the input for global synthesis; do not run raw 8k-message chats straight into vague summary prompts.

## Preferences

Extract by category:

- food/drink
- culture: film, anime, music, books, art, games
- travel style
- date activities
- gifts
- lifestyle: gym, sleep, substances, nightlife
- communication preferences
- sexual preferences and boundaries
- things disliked or avoided

Each preference has polarity (`likes`, `dislikes`, `boundary`, `neutral`), strength, evidence, and last-confirmed date.

## Sexual / Intimacy Model

Sensitive and evidence-backed only. Extract:

- boundaries (explicit and implicit)
- kinks/fantasies
- dirty-talk vs real-life behavior distinction
- consent language
- dominance/submission comfort
- triggers for arousal or shutdown
- physical vs verbal initiation
- what words or framing are accepted/rejected

Never overgeneralize from one flirt exchange. Store as contextual claims with confidence.

## Psychological Profile Dimensions

Do not produce horoscope sludge. Extract claims with evidence and counter-evidence across:

1. Attachment pattern: secure, anxious, avoidant, fearful, mixed
2. Emotional availability: opens up when / shuts down when
3. Defense mechanisms: humor, deflection, withdrawal, minimization, sexualization, reversal
4. Conflict style: avoids, confronts, appeases, jokes, disappears, repairs
5. Vulnerability triggers and shutdown triggers
6. Love language / affection expression
7. Agency and initiative: conversation, logistics, intimacy
8. Insecurities: body, age, performance, replaceability, judgment
9. Power dynamics with Monsieur
10. Reliability / consistency
11. Emotional triggers: jealousy, distance, challenge, direct vulnerability
12. Best interaction strategy

## Dynamic With Monsieur

Separate the person’s general profile from their dynamic with Monsieur:

- who initiates most
- who relaunches after silence
- who validates whom
- who sexualizes
- who proposes logistics
- who repairs tension
- who holds emotional power by period
- push/pull cycles
- what messages worked or failed
- how jealousy affects both sides

## Communication Style

Extract:

- average message length
- language and grammar patterns
- emoji use
- response timing
- directness
- question-answering behavior
- topics that speed response
- topics that create silence
- humor style
- accepted flirt intensity

## Monsieur’s Per-Contact Style

Kardex must learn how Monsieur writes with each contact:

- language used
- short/long message pattern
- spelling/grammar quirks
- teasing style
- sexual directness
- emoji repertoire
- escalation style
- templates that worked
- messages that failed

This is required for future draft/auto-reply features.

## Open Loops

Track unresolved items:

- unanswered question
- plan not scheduled
- promise not fulfilled
- emotional disclosure not acknowledged
- jealousy unresolved
- date to organize
- opportunity window with deadline
- sensitive topic to avoid or revisit

## Actions

Actions are tactical, not just “reply”:

- reply
- wait / do nothing
- follow up
- schedule meeting
- repair tension
- escalate intimacy
- de-escalate
- ask information
- send resource
- check in
- avoid topic
- switch channel

Each action stores priority, deadline, reason, risk, suggested message style, and what not to say.

## Current Relationship State

Recompute after each new message:

- temperature: cold/neutral/warm/hot/conflict
- sexual tension
- trust
- conflict level
- last speaker
- who owes reply
- current topic
- open loops
- opportunity windows
- next best action
- risk notes

## Emotional Memory

Preserve emotionally important moments:

- grief, illness, injury, death of pet/family member
- pride, fear, shame, vulnerability
- reassurance requests
- moments Monsieur hurt, reassured, excited, frustrated, or supported them
- emotional anniversaries

## Recommendations and Shared Backlog

Track things recommended or shared:

- films, anime, books, music, restaurants, bars, hotels, activities, gifts
- who recommended it
- status: not tried, tried, discussed
- evidence and follow-up potential

## Health / Body / Work / Ambitions

Extract sensitively:

- injuries, illness, energy, sleep, substances, mental health
- body image, sport, gym, diet
- job, burnout, career changes, business projects, money concerns, ambitions

## Boundaries and Risks

Extract:

- words/topics that bother them
- sexual/emotional/logistical boundaries
- red flags
- misunderstanding risks
- cultural sensitivities
- what makes Monsieur look needy/cold/aggressive
- consent ambiguity

## Contradiction and Evolution

People change. Store validity periods:

- old claim
- new claim
- evidence for change
- valid_from / valid_to
- confidence trend

## Metrics

Compute where possible:

- messages per week/month
- average reply latency by person
- initiation ratio
- question/answer ratio
- flirt/logistics ratio
- sexual tension score by period
- conflict score by period
- silence gaps
- repair success
- plans made vs executed
- responsiveness after jealousy, compliment, distance, vulnerability

## Views Needed

- short view before replying
- full dossier
- strategic next-reply view
- risk view
- events/anniversaries view
- raw history view
- evidence view for any claim

## Quality Rules

1. No claim without evidence.
2. No aliases from sexual/joke/generic terms.
3. Separate facts, interpretations, strategies, and hypotheses.
4. Events are meaningful, deduplicated, and episode-level.
5. Psychological profile cites message patterns.
6. Current state uses latest messages.
7. Corrections from Monsieur become extraction rules.
8. Raw data is immutable; synthetic layers are replaceable.
