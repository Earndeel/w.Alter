# Bedrock Model Access Troubleshooting

## Error → Cause → Fix Decision Tree

```
Invoke Bedrock model fails
├─ AccessDeniedException: "not available for this account"
│   ├─ Check EULA: create_foundation_model_agreement → "Agreement already exists"?
│   │   ├─ YES → EULA done. Check quotas (see bedrock-mantle zero-quotas below)
│   │   └─ NO → Accept EULA first (API), then submit use case form (console)
│   ├─ Check quotas: get-service-quota L-8528F119 → Value=0.0?
│   │   ├─ YES → bedrock-mantle quota bug. Request SQI >20M. Wait 24-72h.
│   │   │        If CASE_OPENED >24h → escalate via existing SQI cases (see sqi-case-escalation.md)
│   │   │        This is the MOST COMMON cause on free-tier accounts.
│   │   │        Opus 4.7/4.8/Fable 5/Haiku 4.5 all hit this.
│   │   └─ NO (non-zero) → Check SaaS registration (see Section below)
│   │       └─ AWS Console → "Claude Platform" → "Sign up"
│   │       └─ NOT Marketplace "Set up your account" (broken 2026-06)
│   └─ Still stuck? → Escalate via existing SQI cases (see sqi-case-escalation.md)
│       or open Billing support case (free) or contact AWS Sales (last resort)
├─ ResourceNotFoundException: "Model use case details have not been submitted"
│   └─ Anthropic only → Submit use case form via Model Catalog page
├─ ThrottlingException: "Too many tokens per day"
│   ├─ New account with zero usage → Quotas stuck at 0 (bedrock-mantle bug)
│   │   └─ Fix: request quota increase with DesiredValue=20000001.0 (>20M phantom default)
│   │   └─ Note: Opus 4.5/4.6 return ThrottlingException; 4.7+/Fable return AccessDeniedException (same root cause!)
│   └─ Account with actual usage → Daily quota reached → Wait 24h for reset
├─ ValidationException: "Invocation of model ID ... with on-demand throughput isn't supported"
│   └─ Wrong model ID format → Use inference profile prefix (us.anthropic.*)
├─ ValidationException: "The provided model identifier is invalid."
│   └─ Outdated/incorrect ID format (e.g. `us.anthropic.claude-opus-4-8-20260213-v1:0` or `us.anthropic.fable-5-20260213-v1:0`)
│       └─ Use the correct inference profile/model ID (e.g. `us.anthropic.claude-opus-4-8` or `us.anthropic.claude-fable-5`)
├─ AccessDeniedException: "User is not authorized to perform: bedrock:InvokeModel"
│   └─ IAM permission missing → Attach AmazonBedrockFullAccess policy
└─ ThrottlingException (generic)
    └─ Rate limit → Implement backoff or request limit increase
```

## Key Insight: ACTIVE ≠ Enabled ≠ Quotas > 0

Three layers of "does it work":

| Layer | API/Check | Meaning |
|---|---|---|
| `ACTIVE` | `list-foundation-models` | Model exists on Bedrock |
| EULA accepted | `create_foundation_model_agreement` → "already exists" | License to use |
| **Quotas > 0** | `get-service-quota` L-8528F119 Value≠0 | **Actual throughput** |

All three must be satisfied. `ACTIVE` + EULA done + quotas at 0 = `AccessDeniedException` on newer models (misleading).

## Anthropic-Specific: Two-Step Activation (2026-06)

The old `#/modelaccess` page is retired. Most providers auto-enable. **Anthropic is the exception:**

1. **EULA agreement** — API: `list_foundation_model_agreement_offers` → `create_foundation_model_agreement`
2. **Use case form** — Console-only. Yellow banner on `#/modelcatalog`. Schema not available for API.

Both required. Neither alone sufficient. **However**, even after completing both, models on `bedrock-mantle` (Opus 4.7+, Fable 5, Haiku 4.5) still won't work until quotas are > 0. The three-layer checklist is: EULA ✅ → Use case form ✅ → **Quotas > 0** (the most common remaining blocker). Don't assume the use case form is the issue if it's already submitted — check quotas.

### AccessDeniedException on Newer Models (Fable 5, Opus 4.7/4.8) — Quota-Driven

**This is the most confusing Bedrock error pattern.** Newer models on the `bedrock-mantle` endpoint return `AccessDeniedException` when their quotas are at 0 — even though the model IS "auto-enabled" and the EULA IS accepted. The error message says "not available for this account" and suggests contacting AWS Sales. **This is misleading — it's the quotas, not a true access denial.**

**Root cause**: bedrock-mantle quotas are set to 0 for newer models. Unlike older models (Opus 4.5/4.6) which return `ThrottlingException` when quotas are zero, newer models return `AccessDeniedException` — same root cause, different error code.

| Model Family | Quota Endpoint | Zero-Quota Error | Status |
|---|---|---|---|
| Opus 4.5, 4.6 | standard Bedrock | `ThrottlingException` | ✅ Accessible, just throttled |
| Opus 4.7, 4.8 | bedrock-mantle | `AccessDeniedException` | ❌ Blocked until quotas > 0 |
| Fable 5 | bedrock-mantle | `AccessDeniedException` | ❌ Blocked until quotas > 0 |
| Haiku 4.5 | bedrock-mantle | `AccessDeniedException` | ❌ Blocked until quotas > 0 |

**How to distinguish quota-driven AccessDenied from EULA-driven:**
1. Run `create_foundation_model_agreement` → if it returns `Agreement already exists`, EULA is done
2. Submit use case form via console
3. If STILL `AccessDeniedException` → it's the quotas (bedrock-mantle = 0)
4. Check: `aws service-quotas get-service-quota --service-code bedrock --quota-code L-8528F119` → if Value=0.0, that's the cause

**Fix**: Request SQI increase with `DesiredValue=20000001.0` (see "Quota Stuck at Zero" below). No other way to fix this — the "contact AWS Sales" suggestion in the error message is not actionable for this case.

### AWS Marketplace Entitlements + SaaS Registration (Fifth Layer)

Marketplace subscriptions are **separate** from EULA, quotas, and use case form. The full stack:

1. **EULA agreement** (API) → license to use the model
2. **Use case form** (console) → Anthropic requirement
3. **bedrock-mantle quotas** (SQI) → actual throughput
4. **Marketplace agreement** (Marketplace console) → pricing/entitlements
5. **SaaS registration** (Claude Platform on AWS) → links AWS account to Anthropic platform

#### ⚠️ Marketplace "Set up your account" Button Is BROKEN (2026-06)

The "Set up your account" button in **AWS Marketplace → Manage subscriptions** redirects to the Bedrock home page instead of Anthropic's SaaS registration. This is a known issue observed on multiple browsers and accounts.

#### Correct SaaS Registration Flow

Per official AWS docs (https://docs.aws.amazon.com/claude-platform/latest/userguide/setup.html):

1. AWS Console → search **"Claude Platform"** → click **"Claude Platform on AWS"**
2. Click **"Sign up"** (NOT "Set up your account" from Marketplace)
3. Wait for provisioning (a few minutes, no progress bar)
4. Redirected to platform.anthropic.com
5. If "Signed in as a different account" → log out and continue with your email
6. Default workspace is provisioned automatically
7. Note workspace ID for API access
8. Sign in to Claude Console via AWS IAM federation

**Key differences from Marketplace flow:**
- Marketplace "Set up your account" → BROKEN (redirects to Bedrock home)
- "Claude Platform on AWS" → "Sign up" → WORKS (official Anthropic flow)
- This provisions a NEW Anthropic organization tied to your AWS account

## Distinguishing Error Types

| Error | Meaning | Action |
|-------|---------|--------|
| `AccessDeniedException` (model, EULA not accepted) | EULA missing | Accept via API + use case form |
| `AccessDeniedException` (model, EULA accepted) | **Quotas at 0** (bedrock-mantle) | Request SQI >20M, wait 24-72h |
| `ResourceNotFoundException` | Use case form missing | Submit via console |
| `ThrottlingException` (tokens/day, zero usage) | Quotas stuck at 0 (standard endpoint) | Request increase >20M |
| `ThrottlingException` (tokens/day, with usage) | Daily quota reached | Wait 24h |
| `ThrottlingException` (rate) | Per-second limit | Backoff/retry |
| `ValidationException` (invalid identifier) | Using date-suffixed IDs (e.g. `us.anthropic.claude-opus-4-8-20260213-v1:0` or `us.anthropic.fable-5-20260213-v1:0`) which don't exist | Use the correct inference profile / model ID: `us.anthropic.claude-opus-4-8` or `us.anthropic.claude-fable-5`. Check actual IDs with `list-inference-profiles` or `list-foundation-models`. |

## Quota Stuck at Zero (bedrock-mantle Endpoint)

**Root cause**: New free-tier accounts have quotas set to 0 on the `bedrock-mantle` endpoint. The API's "default" value is 20M tokens/min, but the actual value is 0. Standard quota increase requests fail with "must be greater than default value of 2.0E7".

**Diagnosis**: `aws service-quotas list-service-quotas --service-code bedrock` → filter for `Value==0 && Adjustable==true`.

**Fix**: Request with `DesiredValue=20000001.0` (just above 20M). Requests go PENDING → APPROVED (minutes to hours). Key codes:
- L-8528F119: Input tokens/min Opus 4.8
- L-37491D63: Output tokens/min Opus 4.8
- L-54814DC6: Input tokens/min Opus 4.7
- L-15CD18AC: Output tokens/min Opus 4.7

**Pitfall: CASE_OPENED on Free-Tier Accounts**

On accounts without AWS Premium Support, SQI requests for bedrock-mantle quotas go to `CASE_OPENED` status instead of auto-`APPROVED`. This means an AWS support case is opened internally.

- `CASE_OPENED` typically resolves in **24-72h** automatically
- **You CAN interact with CASE_OPENED cases** — they create real AWS Support cases visible in the case history. Add communications to escalate (see `references/sqi-case-escalation.md`)
- You **cannot submit new SQI requests** while 19+ are open (`QuotaExceededException`)
- Only request quotas for models you actually plan to use — previous sessions submitted 19+ SQI for irrelevant models which blocked all new requests for days

**Monitoring pattern**: Set up a cron that tests model invocation periodically. Only notify on success — stay silent during `ThrottlingException` / `AccessDeniedException`:

```
# Cron prompt (every 2h):
"Test Bedrock: aws bedrock-runtime converse --model-id anthropic.claude-haiku-4-5-20251001-v1:0.
If success → report 'Bedrock LIVE', then test Opus 4.8 and Fable 5.
If error → silent (no notification)."
```

**Pitfall: Too Many Requests**

**Escalation options** (in order of effectiveness):
1. **Add communications to existing SQI cases** (free, works on Basic Support) — see `references/sqi-case-escalation.md`
2. **Open new Billing support case** (free) — see `references/billing-support-case-template.md`
3. **Post on AWS re:Post** (free) — requires root email+password or IAM console user

## API Methods

| Method | Purpose |
|--------|---------|
| `list_foundation_model_agreement_offers(modelId)` | Get offerToken for EULA |
| `create_foundation_model_agreement(modelId, offerToken)` | Accept EULA (HTTP 202). Returns `ValidationException: Agreement already exists` if already accepted — this is normal, not an error. |
| `get_foundation_model(modelIdentifier)` | Model details + inferenceTypes |

## Console URL

```
https://us-east-1.console.aws.amazon.com/bedrock/home?region=«secret:vault»#/modelcatalog
```

## Hermes Behavior

- Uses `ConverseStream` API, NOT Messages API
- Strips `us.anthropic.` prefix → sends `anthropic.claude-opus-4-8`
- Both fail identically until model is enabled
- Gateway restart required: `systemctl --user restart hermes-gateway`
