# Gmail Opportunity Intelligence Reference

## Safe extraction record

Use one record per project or offer:

```text
account: <source Gmail address>
message_date: <RFC-2822 date>
sender: <display name + domain>
subject: <subject>
classification: current | incomplete | referral | credit-prize | historical | suspicious
role_or_task: <plain-language description>
compensation: <exact wording; distinguish cash, gross, credit, prize, commission>
hours_duration: <stated commitment and duration>
eligibility: <country/residence, language, device, experience, work authorization>
status: invitation | pending | assessment | rejected | accepted | unknown
freshness: <date/deadline and whether availability was verified>
privacy_risk: none | review | high
verdict: <why it is or is not worth pursuing>
next_action: <dashboard check, verify, ignore, or ask approval>
```

Never copy OAuth tokens, signed URLs, OTPs, passwords, raw personal messages, or unnecessary order/customer data into the record.

## Query bank

Start broad and date-bound:

```text
in:anywhere after:YYYY/MM/DD {hiring recruit job jobs opportunity opportunities internship freelance paid earn earning commission referral money reward income}
```

Then narrow by sender/project:

```text
in:anywhere after:YYYY/MM/DD (from:oneforma.com OR from:centific.com OR from:appen.com OR from:welocalize.com OR from:telusinternational.ai)
in:anywhere ("application status" OR shortlisted OR "next step" OR rejected OR selected OR assessment OR onboarding)
in:anywhere ("referral program" OR affiliate OR commission OR "cash reward" OR "paid study" OR "review reward" OR "store credit")
```

Use `in:anywhere` deliberately. Search `INBOX` alone misses archived, categorized, and sent-thread context. Page actual IDs; estimates are not reliable counts.

## Candidate-body extraction

1. List IDs and metadata first.
2. Fetch `format=full` only for shortlisted IDs and keep IDs mapped to their originating account.
3. Recursively walk MIME parts; prefer non-empty `text/plain`, otherwise clean `text/html`.
4. Apply `html.unescape()`, remove script/style blocks, convert `<br>`, paragraph, list, table, and heading boundaries to newlines, then strip remaining tags and normalize whitespace.
5. Redact tracking/query URLs in logs and intermediate output.
6. Search the cleaned body for `compensation`, `rate`, `hour`, `per task`, `weekly`, `duration`, `location`, `reside`, `native`, `requirements`, `device`, `payment`, `deadline`, `referral`, `bonus`, and `privacy`.

Use bounded retrieval. A large candidate set should be narrowed by date, sender, subject, or thread before full-body reads. Verify any batching implementation before relying on it; do not trade a small bounded read for an unverified broad dump.

## Ranking rubric

Score each lead qualitatively from 0–3 on each dimension:

- **Eligibility fit:** residence, language, device, legal/work status.
- **Skill fit:** actual experience versus generic marketing match.
- **Compensation clarity:** exact cash rate and payment terms versus “competitive” or “up to.”
- **Volume:** stated hours, duration, task availability, and realistic continuity.
- **Freshness:** recent message, explicit deadline, or verified current dashboard status.
- **Risk:** privacy burden, suspicious sender/domain, payment request, or unclear data use (reverse score).
- **Effort:** certifications, assessments, travel, or onboarding burden (reverse score).

A high nominal rate does not outrank a lower rate if the high-rate lead is old, location-locked, limited-slot, unpaid until conversion, or unclear about volume.

## Interpretation rules

- `Remote` still requires checking country/residence and work authorization.
- An invitation is not a contract; an application-pending message is not selection.
- `Competitive salary`, `up to`, `chance to win`, and `earn rewards` are not confirmed income.
- Referral/affiliate revenue depends on conversion and audience; show the mechanism, not a fantasy monthly total.
- Store credit, platform balance, free months, discounts, and prizes must be separated from cash.
- A prior “move forward” status can be superseded by a later rejection or inactivity.
- Duplicates across addresses may indicate duplicate platform profiles; recommend using the already-configured profile rather than creating another account.

## Privacy and abuse checks

Escalate or deprioritize messages requesting:

- raw e-commerce receipts, order confirmations, refunds, or shipping messages;
- SMS containing OTPs, PINs, verification codes, or other authentication artifacts;
- face/selfie/video recordings without clear compensation and retention terms;
- payment, password, or bank details through an email link;
- urgent prizes, account suspensions, parcel claims, or impersonated brands from unrelated/random domains.

For suspicious mail, report the sender/domain and reason without opening links. Do not treat it as a money opportunity.

## Report format

1. **Executive verdict:** number of serious current leads, strongest lead, and main blocker.
2. **Top table:** project, account, date, exact compensation, eligibility, freshness, verdict.
3. **Per-account findings:** current leads, incomplete leads, historical/status context, and ignored marketing/spam.
4. **Location reality check:** explicitly compare requirements with Monsieur’s known current location; do not infer global eligibility from “remote.”
5. **Safety notes:** data/privacy and phishing concerns.
6. **Action boundary:** state that no links were opened, no applications submitted, and no messages sent unless explicitly authorized.

Use exact dates, quote compensation accurately, and label any arithmetic as hypothetical gross income with no guarantee of hours or acceptance.
