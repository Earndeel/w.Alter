---
name: gmail-opportunity-intelligence
description: "Use for multi-account Gmail job and revenue analysis."
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [Gmail, Email, Jobs, Freelance, Revenue, Research, Privacy, Multi-account]
    related_skills: [google-workspace, google-workspace-multi-account]
---

# Gmail Opportunity Intelligence

Use this skill when Monsieur asks for a deep, read-only review of one or more Gmail accounts to identify job offers, freelance work, paid studies, affiliate/referral income, business leads, or other legitimate ways to earn money.

This is an intelligence workflow, not an application workflow. Never apply, create an account, click an external offer link, submit a survey, or send an email unless Monsieur explicitly authorizes that side effect.

## Operating principles

- Search across all Gmail folders with `in:anywhere`; do not limit the review to Inbox.
- Start with metadata and search results, then fetch full bodies only for shortlisted candidates. Do not download thousands of newsletters or receipts unnecessarily.
- Treat an invitation, newsletter, referral promotion, or “up to” claim as a lead—not as confirmed employment or income.
- Keep each message ID tied to the account/token that produced it. Gmail message IDs are account-scoped; never reuse an ID against another account.
- Do not print, expose, persist, or forward OAuth tokens, credential-file contents, signed tracking URLs, magic links, OTPs, or other secrets.
- Preserve account boundaries in the report: every finding must identify the source account, sender, date, and subject.
- “Remote” is not equivalent to worldwide eligibility. Read explicit residence, country, language, device, schedule, and work-authorization requirements.
- Distinguish cash, gross hourly pay, account credit, discounts, prizes, referrals, and unpaid surveys. State the distinction plainly.

## Workflow

### 1. Establish scope and account inventory

1. Load the Google Workspace skill and its Gmail search reference before using the API.
2. Identify the authorized account profiles without displaying token contents. Use the Gmail profile endpoint to map each credential to the actual address.
3. Record only safe metadata: address, message count if useful, search period, and read-only scope. Do not modify labels or mark messages read.
4. State the review boundary honestly: metadata may be scanned broadly while only candidate messages are opened in full.

### 2. Run a broad candidate scan

Use date-bounded searches first, then sender- or project-specific searches. Useful broad terms include:

#### Multi-account routing and query validation

- Run each discovery query once per isolated account home. A single Gmail token does not search the other connected mailboxes; preserve the account label beside every message ID and result.
- Verify each token with `users.getProfile` before scanning, then use that exact identity in the report. Never silently correct a near-match address or infer that two mailboxes share one profile.
- Fetch a candidate only through the account/token that produced its ID. A `404 Requested entity was not found` during `gmail get` is a routing signal: re-run the search in the source account rather than retrying the same ID against another token.
- Treat a zero-result complex Gmail query as unvalidated, not as evidence that no opportunity exists. Decompose it into explicit parenthesized `OR` clauses, run a known-sender smoke test, and compare per-account results before concluding that the lead is absent.
- Keep the broad scan metadata-first. Open only shortlisted bodies, and redact signed links, magic links, KYC links, and tracking parameters from intermediate notes or the report.

```text
in:anywhere after:YYYY/MM/DD {hiring recruit job jobs opportunity opportunities internship freelance paid earn earning commission referral money reward income}
```

Run additional focused searches for:

- known work platforms: `oneforma.com`, `centific.com`, `appen.com`, `welocalize.com`, `telusinternational.ai`, `linkedin.com`, `indeed.com`, `upwork.com`, `malt.fr`;
- project/status terms: `application`, `shortlisted`, `next step`, `rejected`, `selected`, `assessment`, `onboarding`;
- revenue terms: `affiliate`, `referral program`, `commission`, `cash reward`, `paid study`, `review reward`, `store credit`.

Page through actual message IDs. Do not rely on `resultSizeEstimate` for counts or cleanup decisions.

### 3. Retrieve and normalize candidate bodies

For shortlisted IDs, use `format=full` and parse MIME parts recursively:

1. Prefer a non-empty `text/plain` part.
2. Fall back to `text/html`.
3. Apply `html.unescape()`, remove scripts/styles/tags, convert block elements to line breaks, and normalize whitespace.
4. Redact URLs to a safe domain or `[LINK]` in intermediate output; preserve no query strings or tracking parameters.
5. Keep the original sender/date/subject and message ID internally for traceability.

When a search returns many messages, stay metadata-first and narrow by date, sender, and subject before retrieving bodies. Only use batching after verifying the API endpoint in the current environment; a smaller, bounded sequential read is safer than a broad body dump.

### 4. Extract an opportunity record

For each candidate, extract:

- source account;
- sender domain and date;
- offer/project/company;
- exact role or task;
- compensation and payment unit;
- expected hours, duration, and payment timing;
- location/residence and language requirements;
- device, certification, education, or experience requirements;
- application state (invitation, application pending, assessment, rejection, acceptance, or unknown);
- deadline or freshness;
- data/privacy obligations;
- link/domain safety notes;
- confidence and next action.

For hourly approximations, calculate with a tool and label them as gross, hypothetical, and non-guaranteed. Never silently convert currencies or imply that stated hours are assured.

### 5. Deduplicate and classify

Group duplicate mailings by project, sender, subject family, and account. Preserve account-specific copies when they may represent separate platform profiles, but flag the duplication so Monsieur does not create another account or apply twice.

Classify every finding as one of:

1. **Current concrete opportunity** — role, conditions, and compensation are stated.
2. **Current but incomplete lead** — project is plausible but rate, volume, or eligibility is missing.
3. **Referral/affiliate income** — commission depends on conversions or an audience.
4. **Credit/discount/prize** — not cash income; report separately.
5. **Historical or expired** — retain as context but do not present as actionable.
6. **Suspicious/phishing** — urgency, impersonation, random domains, prize/account-lock claims, or requests for sensitive data.

Invitation ≠ hiring. “Application pending” ≠ selection. “Competitive salary” ≠ a known salary. “Up to” ≠ expected income.

### 6. Rank by practical value

Use a qualitative ranking based on:

- location and legal eligibility;
- skill/profile fit;
- compensation clarity;
- realistic volume and duration;
- recency and deadline;
- privacy and scam risk;
- effort to apply or qualify.

Prioritize a lower-paying lead with clear eligibility and volume over a flashy maximum rate that is old, location-locked, limited-slot, or unpaid until conversion.

### 7. Report without taking action

Lead with the shortlist and the honest verdict. Then report by account, with exact dates and evidence from the email. Include:

- the top opportunities and why they rank;
- eligibility blockers, especially residence requirements;
- old/expired items;
- referral, credit, and marketing claims separated from jobs;
- privacy/phishing warnings;
- what was not done (no clicks, applications, submissions, or sent mail).

If Monsieur wants follow-up, ask which shortlisted items may be opened or applied to; external submissions require a fresh approval gate.

## High-value pitfalls

- OneForma and similar platforms may send identical projects to multiple Gmail addresses. Use the existing profile with certifications/payment setup; do not create a duplicate profile merely because a second inbox received the invitation.
- Data-collection projects may request e-commerce messages, voice recordings, selfie videos, or OTP-like SMS. Do not recommend submission until compensation and data handling are clear; redact or refuse sensitive material as appropriate.
- A current email can still describe a role that has filled. Mark availability as “according to the email” unless verified in the official account or an authoritative current source.
- Old applications are valuable for status history: a 2024 “move forward” message is not proof of current hiring, and a later rejection supersedes an earlier invitation.
- Daily job digests often contain many remote roles with no salary, location, or contract details. Summarize representative roles, not every marketing card.
- **"Automate 100%" must be scoped to the periphery, not the task.** The paid data-labelling roles (OneForma, RWS, Appen, TELUS) carry explicit anti-AI/anti-LLM clauses — use of ChatGPT/Copilot/VPN to do the work = non-payment + immediate exclusion (RWS wording) or a permanent ban (the Fiverr DAC7/flag pattern). The legitimate, 100%-automatable slice is the surrounding pipeline: dashboard monitoring for new matching projects, prompt application, certification/KYC/payment-method onboarding, document signing, duplicate-profile reconciliation. Recommend that split honestly instead of promising to automate the judgement task.
- **"Remote" still has residence locks.** Most French-locale roles state "must be located in France"; some Europe-wide roles exclude Spain. Check Monsieur's actual residence against the requirement before ranking a role as accessible — a Bangkok-based operator cannot take France-only work.
- **Duplicate platform profiles block payouts.** OneForma and similar send the same invitation to several inboxes and may already hold an account under another address ("You already have an account with us", with a different slug). Reconcile the existing profile before subscribing/creating a second one.
- **Platform logins live in Bitwarden, not the vault** (verified 2026-08). When follow-up is authorized, check `bw list items` first; known items: `my.oneforma.com` (5 profiles: Earndeel, lucas.jouvencon@gmail.com ×2, lucas.jouvenson@gmail.com, LucasJ96), `sdl-prod.eu.auth0.com` (the SSO for **RWS WorkZone** at sdl.appiancloud.com), `app.crowdgen.com` / `account.appen.com` / `connect.appen.com` / `identity.appen.com` (Appen), `telusinternational.headway.ai` (multiple), `identity.welocalize.com`, `fr.fiverr.com`, `nordaccount.com` / `ucp.nordvpn.com`. Passwords are stored per item; never print them, use them in the browser flow only.
- **Login flows are Cloudflare-gated (managed Turnstile)** — email/password forms silently fail until the invisible captcha token is produced. The reliable path is **"Sign in with Google" via the user's Mac Brave cookies** (account chooser lists linked identities) and resolving the Turnstile inside ONE persistent browser profile (cf_clearance is fingerprint-bound). See the `vpn-exit-routing` skill for the container-proxy + Turnstile + LINK_CONFIRMATION playbook before attempting any platform login.

## Reference

See `references/gmail-opportunity-intelligence.md` for the compact extraction schema, query bank, ranking rubric, and privacy-safe report format. See `references/data-labelling-platforms.md` for a living knowledge bank of the EU/FR microtask platforms (OneForma, RWS/TrainAI, Alignerr, Appen/CrowdGen, TELUS, Fiverr) with rates, onboarding gates, and anti-LLM clauses.
