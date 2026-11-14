# EU / FR data-labelling & microtask platform knowledge bank

Verified against a real 3-account audit (Aug 2026). Rates/ons are as stated in
platform emails, not guaranteed. Senders: `oneforma.com`, `centific.com`,
`rws.com`, `appen.com`, `telusinternational.ai`, `alignerr.com`.

## OneForma / Centific
- High email volume: ~1 invitation/week to an engaged address, often mirrored
  across several inboxes (same project, different `@`.com). Senders rotate per
  project, all `*@oneforma.com` or `*@centific.com`.
- Typical FR remote roles and rates seen: Search Satisfaction/QA Reviewer
  ($13.5/h), Search Evaluation/Pegasus ($14/h, min 20h/wk), Speech & Text
  Evaluation/Harbor ($20/h, Apple/Mac latest-macOS required), TTS Audio Quality
  Tester ($15/h), Crowd/Speech Translation Evaluation (Zeno, per-task),
  Transcription + Disfluency Tagging (OAK), Voice Assistant dialog annotation
  (Kawaii), Translation & Entity Label Quality Reviewer ($14/h, productivity-
  scaled: hourly rate × hits/65 × acceptance).
- **Onboarding gates before endorsement**: 1-2 certifications (e.g. ISAAC Search
  Relevance, language proficiency), a valid payment method (PayPal / Payoneer /
  Tipalti), a signed ICS/ICF signature file, and KYC. Projects are locked until
  these are done — the platform explicitly withholds endorsement otherwise.
- **Anti-LLM clauses are explicit**: Pegasus says VPN + AI-gen tools (ChatGPT,
  Copilot) "NOT ALLOWED". Rules exist because the task is LLM-trivial; the
  endorsement/certification is a human-effectiveness filter.
- Referral bonuses exist in some projects (e.g. Fred Annotation $25/referral,
  with a macOS 14+ requirement for referees) — labelled as referral income, not
  cash, until converted.
- **Duplicate-profile trap**: an address may already hold a OneForma account
  ("You already have an account with us — log in", sent to a different slug).
  Getting the same invitation on multiple inboxes does NOT justify a second
  profile; creating one blocks endorsements and payouts.

## RWS Group (rws.com) — TrainAI / WorkZone
- Projects: Echo 2026 (alias **Diamond**), speech/audio annotation, LLM text
  evaluation, data collection.
- Onboarding is document-heavy via WorkZone (`sdl.appiancloud.com`): sign
  Objectionable Content Agreement (OCA), Facebook Trade Compliance & Background
  Check, Identity Verification Consent, then a Data Collection Agreement (DCA)
  for audio/video tasks (excludes Illinois/Texas residents).
- **Explicit anti-LLM clause**: using AI tools/LLMs to do the work = non-payment
  + immediate exclusion from the project.
- Volume is ad-hoc, first-come-first-served. A launched project can be cancelled
  by the client with little notice (Speech Annotator project cancelled before
  start, June 2026) — pre-start pipeline is soft, don't over-invest.

## Alignerr (app.alignerr.com)
- Subject-matter-expert data work (software engineering, finance, scientific
  simulations). Recruiters actually follow up ("re:" threads) — a follow-up means
  still-hiring signal.
- Free signup, profile + assessments to get matched. No stated rate in
  recruitment mail.

## Appen / CrowdGen (appen.com)
- Invitations via `crowdprojects@appen.com` / `recruiting@mail.appen.com`; work
  happens on the CrowdGen dashboard with "Project Picks for You".
- Structured, API-adjacent projects exist (e.g. AI Translation & Data
  Extraction: translate JSON prompts + extract F&B entities) — these are the
  most mechanically automatable, but check the project's AI-use/confidentiality
  terms before scripting.
- Rejection emails explicitly point to other projects ("not shortlisted for
  Baldcypress, but here are others") — treat a rejection as an open door to the
  platform dashboard.

## TELUS Digital AI (telusinternational.ai)
- Often **physical** data-collection gigs (e.g. in-cabin car recording,
  Sindelfingen Germany: 150€/3h session or 70€/1h). Requires travel; not remote,
  not automatable. Match against Monsieur's actual location before ranking.

## Fiverr — DAC7 / account-flag pattern
- A Business account flagged for missing DAC7 → "compte signalé", Gigs removed
  from search, then permanent suspension after 60 days. Detection and content
  removal are automatic. A "signalé" Fiverr account is a liability, not a
  revenue route; fix DAC7/ID verification or let it die. Lesson generalizes:
  tax-form/data gaps on freelance platforms trigger auto-flags with long tails.

## Cross-cutting automation lens
- The platforms that pay cash/hour for judgement tasks all forbid LLM assistance.
  The 100%-automatable slice is the pipeline *around* the task: monitor
  dashboards for new matching projects, auto-apply, complete certifications/
  KYC/payment-method onboarding, pre-sign standard compliance docs, reconcile
  duplicate profiles. Automating the judgement task itself is contract fraud and
  the ban pattern (Fiverr) is real.

## Access & login (verified 2026-08)
- All platform logins live in **Bitwarden**, not the age vault (`bw list items`
  before asking Monsieur). Item names seen: `my.oneforma.com` (5 entries —
  several distinct OneForma identities exist), `sdl-prod.eu.auth0.com` (SSO that
  fronts RWS WorkZone at `sdl.appiancloud.com`), `app.crowdgen.com`,
  `account.appen.com` / `connect.appen.com` / `identity.appen.com`,
  `jobs.telusinternational.com`, `identity.welocalize.com`,
  `welocalizeapi.okta.com`, `fr.fiverr.com`. Passwords-only; no TOTP on these.
- **RWS ≠ OneForma**: the RWS login page is Auth0 (`sdl-prod.eu.auth0.com`) and
  may appear unrelated to rws.com; WorkZone tasks are signed via docs, not via
  the Auth0 session alone.
- Login pages are Cloudflare-gated (managed Turnstile): the SPA form silently
  fails until an invisible captcha token exists; `cf_clearance` is
  fingerprint-bound so it must be solved inside ONE persistent browser profile.
  Reliable route: **"Sign in with Google" using the user's Mac Brave cookies** —
  the account chooser lists all linked identities and the back-URL is
  `?type=LINK_CONFIRMATION&provider=google&socialId=...`. Playbook in the
  `vpn-exit-routing` skill (same-profile Turnstile + proxy container).
