# AWS Billing Support Case — Quota Escalation Template

## When to Use

- SQI requests stuck in `CASE_OPENED` for >48h on free-tier accounts
- `bedrock-mantle` quotas at 0 with no automatic approval
- Need to escalate before promotional credits expire
- **Prefer SQI case escalation first** — see `references/sqi-case-escalation.md` for a faster approach that works by adding communications to existing SQI-generated cases (no form filling needed)

**Cost**: Billing Support cases are **free** on all AWS accounts (no paid support plan needed).

## How to Open

### Basic Support Plan (Free Tier) — Amazon Q Gate

**As of 2026-06, Basic Support plan does NOT have a direct "Create case" button.** The Support Center opens an Amazon Q chatbot that acts as a gatekeeper.

1. AWS Console → Support Center → opens **Amazon Q** chatbot (NOT a case form)
2. Type your issue in the Q textarea (e.g. "Bedrock quotas stuck at zero, cannot invoke Claude models")
3. Q investigates (takes 20-30s, shows thinking animation with agent names)
4. After investigation, Q shows options including **"Create a case"** button — click it
5. Case form loads with Q's description pre-filled — edit as needed
6. Select **Billing** as the issue type (free tier) in the "Case type" dropdown
7. Fill in the template below

### Pitfall: Amazon Q Feedback Modal

**Pressing Enter in the Q textarea triggers the FEEDBACK modal, NOT Q submission.** The Q textarea auto-submits after typing — there is no explicit submit step. If the feedback modal appears, click the X to dismiss it. The "Create a case" button appears after Q finishes its investigation (20-30s).

### Pitfall: AWSUI Select Dropdowns in Camoufox

The AWS Support form uses AWSUI Select components (React). These are **extremely slow** in Camoufox — each dropdown interaction takes 10-15s due to DOM complexity. DOM queries timeout at 25s on AWS console pages.

- **Case type**, **Service**, **Category**, **Severity** dropdowns all use AWSUI Select
- Use `click-at` (coordinate-based) with annotated screenshots to interact
- Expect the full form fill to take 5-10 minutes due to dropdown latency
- If automation fails, fill the remaining dropdowns manually via webtop Chromium (port 3001/9223)

## Template

**Subject**: Bedrock model invocation quotas stuck at zero — account [ACCOUNT_ID]

**Description**:

```
Account ID: [ACCOUNT_ID]
Region: «secret:vault»

All bedrock-mantle endpoint quotas for Anthropic Claude models are set to 0.0,
preventing any model invocation despite completing:

1. ✅ Model use case form submitted (Anthropic requirement)
2. ✅ EULA agreement accepted (API — list_foundation_model_agreement_offers + create_foundation_model_agreement)
3. ✅ SQI requests submitted (Status: CASE_OPENED since [DATE])

Affected quotas (all Value=0.0, Adjustable=true):
- L-8528F119: [bedrock-mantle] Input tokens/min for Claude Opus 4.8
- L-37491D63: [bedrock-mantle] Output tokens/min for Claude Opus 4.8
- L-54814DC6: [bedrock-mantle] Input tokens/min for Claude Opus 4.7
- L-15CD18AC: [bedrock-mantle] Output tokens/min for Claude Opus 4.7

Any invocation attempt returns either:
- AccessDeniedException: "anthropic.claude-opus-4-8 is not available for this account"
- ThrottlingException: "Too many tokens per day"

The SQI API incorrectly reports "DesiredValue must be greater than the default quota value of 2.0E7"
even though the current value is 0.0 — this appears to be a known discrepancy between the
bedrock-mantle endpoint and the standard service quota system.

Request: Please reset bedrock-mantle quotas to their default values to enable model invocation,
or manually approve the pending SQI requests.

SQI request IDs: [LIST FROM `aws service-quotas list-requested-service-quota-change-history`]
```

## Key Points

- **Billing** support is free — do NOT select "Technical" (requires paid plan)
- Include SQI request IDs if available (shows you've done due diligence)
- Mention the discrepancy between 0.0 current value and 20M phantom default
- Response time: typically 24-48h for billing cases
- Follow up after 48h if no response

## MFA Note

AWS root account login requires MFA. For this account, MFA is via **authenticator app** (not Bitwarden TOTP). The 6-digit code must come from the user's phone (Google Authenticator, Authy, etc.).

When automating via Camoufox:
1. Navigate to `https://console.aws.amazon.com/support/home#/case/create`
2. Enter email + password from vault (`aws/password`, `bitwarden/email`)
3. At MFA prompt → ask user for 6-digit code (no automation possible)
4. Once authenticated, paste the template above
5. Submit and confirm case number
