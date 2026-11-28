---
name: aws-bedrock-setup
description: Use when Monsieur needs AWS Bedrock credentials, IAM setup, Hermes provider config, model-access verification, or exact Anthropic model IDs. Official catalog first; distinguish catalog availability from account entitlement.
version: 2.5.0
author: W.Alter
metadata:
  hermes:
    tags: [aws, bedrock, claude, credentials, iam, provider, hermes, free-tier]
    related_skills: [hermes-provider-mastery, vault-lookup]
---

## References

- For current Anthropic model IDs and Bedrock catalogue-versus-account checks, see `references/anthropic-bedrock-model-availability.md`.

# AWS Bedrock Setup

Complete guide to provisioning AWS Bedrock access, configuring it as a Hermes provider, and unlocking free tier credits.

## When to Use

- Setting up AWS Bedrock for the first time
- Adding Claude models via Bedrock to Hermes
- Unlocking free tier bonus credits ($100+)
- Discovering available Bedrock models and pricing
- Rotating or managing AWS credentials

---

## Section 1: IAM User Creation

Create a dedicated IAM user (not root) with Bedrock access.

```bash
aws iam create-user --user-name walter-bedrock
aws iam attach-user-policy --user-name walter-bedrock \
  --policy-arn arn:aws:iam::aws:policy/AmazonBedrockFullAccess
aws iam create-access-key --user-name walter-bedrock
```

When CLI auth isn't available, use headless browser automation (Camoufox/Playwright) to create the user via the IAM console.

---

## Section 2: Credential Storage

Store in vault (never in config files):

```bash
vault set aws/access_key_id AKIA...
vault set aws/secret_access_key ***
vault set aws/account_id <ACCOUNT_ID>
vault set aws/region «secret:vault»
```

Add AWS env vars to the Hermes environment file (same place as KIE_API_KEY etc.):
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION=«secret:vault»`

---

## Section 3: Hermes Provider Config

Two config sections are REQUIRED in config.yaml:

**Section A** — Bedrock global settings:
```yaml
bedrock:
  region: «secret:vault»
```

**Section B** — Provider entry under `providers:`:
```yaml
  bedrock:
    name: Amazon Bedrock
    api_mode: anthropic_messages
    default_model: claude-opus-4-7
    key_env: AWS_ACCESS_KEY_ID
    models:
      - claude-opus-4-8
      - claude-opus-4-7
      - claude-opus-4-6
      - claude-sonnet-4-6
      - claude-sonnet-4-5-20250929
      - claude-haiku-4-5-20251001
      - claude-fable-5
      - claude-3-5-haiku-20241022
      - claude-3-haiku-20240307
```

Restart after changes: `systemctl --user restart hermes-gateway`

---

## Section 4: Free Tier Credit Unlock

AWS offers up to $200 in credits for new accounts (confirmed 2026-06). $100 is automatic on sign-up; $100 is earned by completing 5 onboarding activities ($20 each).

### The 5 Required Activities

| # | Activity | Service | Key Command |
|---|----------|---------|-------------|
| 1 | Launch an instance | EC2 (t3.micro) | `aws ec2 run-instances` |
| 2 | Set up a cost budget | AWS Budgets | `aws budgets create-budget` |
| 3 | Use a Bedrock model | Bedrock | `aws bedrock-runtime invoke-model` |
| 4 | Create an Aurora or RDS database | RDS | `aws rds create-db-instance --db-instance-class db.t3.micro --engine mysql` |
| 5 | Create a web app using Lambda | Lambda | `aws lambda create-function` |

**Detection**: Credits appear within minutes per activity. Check Billing → Credits page. Activities shown on Console Home "Explore AWS" widget. Full CLI recipes: `references/explore-aws-credit-activities.md`.

### Pitfalls

- **t2.micro may not be free-tier** on all accounts. Use `t3.micro` instead.
- **EC2 needs valid AMI + subnet.** Use latest Amazon Linux 2023 AMI.
- **Credits appear per-activity**, not all-or-nothing. Each activity awards $20 within minutes.
- **RDS**: Use `--db-instance-class db.t3.micro --engine mysql` for free-tier eligible. Delete with `--skip-final-snapshot` immediately after credit appears.
- **Lambda**: Requires IAM role first. Create role → attach `AWSLambdaBasicExecutionRole` → create function → invoke once → delete function → detach policy → delete role.
- **Terminate/delete all resources immediately** after each credit appears to avoid charges.
- **Budgets**: `aws budgets create-budget` works via CLI. Budget doesn't incur charges itself.
- **Bedrock invoke**: Use Haiku (cheapest) to satisfy the "use a foundation model" activity.

### EC2 Launch (Amazon Linux 2023, t3.micro)

```bash
AMI=$(aws ec2 describe-images --owners amazon \
  --filters "Name=name,Values=al2023-ami-2023*-x86_64" \
  --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)

SUBNET=$(aws ec2 describe-subnets \
  --filters "Name=default-for-az,Values=true" \
  --query 'Subnets[0].SubnetId' --output text)

aws ec2 run-instances --image-id $AMI --instance-type t3.micro \
  --subnet-id $SUBNET \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=free-tier-test}]'
```

---

## Section 5: Model Discovery & Pricing

### List Models

```bash
aws bedrock list-foundation-models --region «secret:vault» \
  --query "modelSummaries[*].[providerName,modelId]" --output text
```

### Claude Pricing (per MTok, «secret:vault», 2026-06)

| Model | Input | Output |
|---|---|---|
| Opus 4.8 | $5 | $25 |
| Fable 5 | $10 | $50 |
| Sonnet 4.6 | $3 | $15 |
| Haiku 4.5 | $1 | $5 |
| Nova Micro | $0.035 | $0.14 |

### What's NOT on Bedrock

MiMo 2.5 (Xiaomi), GPT 5.5 (OpenAI — only gpt-oss), Kimi K2.6 (only K2.5), MiniMax M3 (only M2.x), Qwen 3.7 (only Qwen3).

### Inference Profile Requirement

Newer models need profile IDs (`us.anthropic.*` prefix) for on-demand invocation. Raw `invoke-model` and `ConverseStream` calls need them explicitly. However, **even with correct inference profile IDs, models won't work until manually enabled** (see Section 7 below).

**Hermes behavior**: When `provider: bedrock`, Hermes uses the Bedrock `ConverseStream` API (NOT the Anthropic Messages API). The model ID sent to the API is `anthropic.claude-opus-4-8` (without `us.` prefix) — Hermes normalizes the ID. This means **both raw and inference profile IDs fail identically** until model access is enabled in the console.

---

## Section 6: Verification & Testing

Always test with Haiku first (cheapest at $1/$5 per MTok). Don't burn Opus/Fable credits just to verify the endpoint works.

### CLI Quick Test (for cron jobs and scripts)

```bash
# Verify credentials
aws sts get-caller-identity

# Test with cheapest model (Haiku 4.5 via inference profile)
aws bedrock-runtime invoke-model \
  --model-id "us.anthropic.claude-haiku-4-5-20251001-v1:0" \
  --region «secret:vault» \
  --content-type "application/json" \
  --accept "application/json" \
  --body '{"anthropic_version":"bedrock-2023-05-31","max_tokens":10,"messages":[{"role":"user","content":"Say OK"}]}' \
  /tmp/bedrock_test.json

# Read response
cat /tmp/bedrock_test.json
```

**Exit code 0** = model is live. **Exit code 255** = check error type:
- `AccessDeniedException` → model access not enabled (see Section 7)
- `ThrottlingException` → quotas at 0 or daily limit (see Section 7b)
- `ValidationException` → wrong model ID format

### Python boto3 Test

```bash
python3 -c "
import boto3, json
c = boto3.client('bedrock-runtime', region_name='«secret:vault»')
r = c.invoke_model(modelId='us.anthropic.claude-haiku-4-5-20251001-v1:0',
  body=json.dumps({'anthropic_version':'bedrock-2023-05-31','max_tokens':50,
    'messages':[{'role':'user','content':'ping'}]}))
print(json.loads(r['body'].read()))
"
```

### Discovering Correct Model IDs

Bedrock model IDs do NOT match Anthropic's direct API IDs. Always discover via API:

```bash
# List all Anthropic models
aws bedrock list-foundation-models --region «secret:vault» \
  --query "models[?providerName=='Anthropic'].modelId" --output text

# List inference profiles (needed for invoke-model CLI)
aws bedrock list-inference-profiles --region «secret:vault» \
  --query "inferenceProfileSummaries[?contains(inferenceProfileId,'anthropic')].inferenceProfileId" --output text
```

**Model ID format rules:**
- Foundation model: `anthropic.claude-opus-4-8` (no date suffix, no `us.` prefix)
- Inference profile: `us.anthropic.claude-opus-4-8` (has `us.` prefix, no date suffix)
- Anthropic direct API: `claude-opus-4-8-20260213` (has date suffix — NOT valid on Bedrock)
- `invoke-model` CLI requires inference profile IDs (`us.` prefix) for INFERENCE_PROFILE-only models
- Hermes normalizes IDs (strips `us.` prefix) and uses `ConverseStream` API

---

## Section 7: Model Access Activation (CRITICAL)

**Models listed as `ACTIVE` in `list-foundation-models` still require manual activation before they can be invoked.** This is the #1 gotcha for new Bedrock accounts.

### Symptoms

```
AccessDeniedException: anthropic.claude-opus-4-8 is not available for this account
ResourceNotFoundException: Model use case details have not been submitted for this account
```

Both errors mean the same thing: the model exists but hasn't been enabled for invocation.

### What `ACTIVE` Actually Means

| Status | Meaning |
|--------|---------|
| `ACTIVE` | Model exists on Bedrock, can be listed |
| `LEGACY` | Older model version |
| **Enabled for invocation** | ✅ Can actually call the API (separate from ACTIVE) |

The `list-foundation-models` API only shows existence, NOT invocation permission.

### The Two-Step Activation Process

As of 2026-06, the old "Model access" page has been retired. Models are "auto-enabled" — **but Anthropic is the exception**. Anthropic requires TWO things before invocation works:

1. **EULA agreement** — Can be done via API (see below)
2. **Use case form** — MUST be submitted via console UI (no API path)

Both are required. Neither alone is sufficient.

### Step 1: EULA Agreement (API)

```python
import boto3
client = boto3.client('bedrock', region_name='«secret:vault»')

# Get offer token
offers = client.list_foundation_model_agreement_offers(
    modelId='anthropic.claude-opus-4-8'
)
offer_token = offers['offers'][0]['offerToken']

# Accept agreement
client.create_foundation_model_agreement(
    modelId='anthropic.claude-opus-4-8',
    offerToken=offer_token
)  # Returns HTTP 202
```

Repeat for each model family you want (opus, sonnet, haiku, fable).

### Step 2: Use Case Form (Console Only)

1. Go to: `https://us-east-1.console.aws.amazon.com/bedrock/home?region=«secret:vault»#/modelcatalog`
2. **Yellow banner** at top: *"Anthropic requires first-time customers to submit use case details before invoking a model"*
3. Click **"Submit use case details"** button
4. Fill form: company name, URL, industry dropdown, intended users (checkboxes), use case description
5. Click **Submit**
6. Green confirmation: *"Use case details for Anthropic submitted successfully"*

**Automating the form via Camoufox:** See `references/bedrock-use-case-form.md` in the camoufox-max-automation skill for the full browser automation recipe.

### Rate Limits on New Accounts

After activation, new free-tier accounts hit **ThrottlingException: "Too many tokens per day"** even with zero usage. This is a default daily token quota that resets every 24h. Wait 24h after account creation before expecting models to work.

```
ThrottlingException: Too many tokens per day, please wait before trying again
```

**ThrottlingException ≠ AccessDeniedException.** Throttling means the model IS accessible — you're just rate-limited. AccessDenied means activation is incomplete.

### Section 7b: Quota Stuck at Zero / Agreement Not Available

**This is the #1 blocker for new free-tier Bedrock accounts and newly launched Anthropic models.** Even after completing the use case form, models may return `ThrottlingException: Too many tokens per day` or `AccessDeniedException: <model> is not available for this account` because critical quotas are set to **0**, or because the model agreement is not yet available for the account.

#### Diagnosis

Always distinguish four Bedrock states before blaming IAM:

```bash
# 1) Model exists and lifecycle status
aws bedrock get-foundation-model \
  --model-identifier anthropic.claude-sonnet-5 \
  --region «secret:vault» --output json

# 2) Account-level availability gates: agreement/auth/entitlement/region
aws bedrock get-foundation-model-availability \
  --model-id anthropic.claude-sonnet-5 \
  --region «secret:vault» --output json

# 3) Inference profile exists for invoke-model
aws bedrock get-inference-profile \
  --inference-profile-identifier us.anthropic.claude-sonnet-5 \
  --region «secret:vault» --output json

# 4) Quotas — look for Value=0 on relevant model quotas
aws service-quotas list-service-quotas --service-code bedrock --region «secret:vault» \
  --query 'Quotas[?Value==`0.0` && contains(QuotaName, `Claude Sonnet 5`)].[QuotaCode,QuotaName,Value,Adjustable]' \
  --output table
```

Interpretation:
- `authorizationStatus=AUTHORIZED`, `entitlementAvailability=AVAILABLE`, `regionAvailability=AVAILABLE`, but `agreementAvailability.status=NOT_AVAILABLE` = model visible but not yet enabled/agreeable for this account. This is common during fresh rollouts.
- `agreementAvailability.status=AVAILABLE` but quotas are `0` = quota/SQI path.
- `ACTIVE` in `get-foundation-model` or `list-foundation-models` only means the model exists on Bedrock; it does **not** prove invocability.

**Observed Sonnet 5 rollout pattern (2026-07-01)**: `anthropic.claude-sonnet-5` was `ACTIVE`, `us.anthropic.claude-sonnet-5` and `global.anthropic.claude-sonnet-5` inference profiles were `ACTIVE`, but invocation failed with `AccessDeniedException: anthropic.claude-sonnet-5 is not available for this account`. `get-foundation-model-availability` showed `agreementAvailability.status=NOT_AVAILABLE`; Sonnet 5 token quotas were also `0`. Conclusion: account-level AWS/Anthropic gating, not IAM or wrong model ID.

#### Zero-quota scan

```bash
# Check all Bedrock quotas — look for Value=0 on adjustable quotas
aws service-quotas list-service-quotas --service-code bedrock --region «secret:vault» \
  --query 'Quotas[?Value==`0.0` && Adjustable==`true`].[QuotaCode,QuotaName,Value]' \
  --output table
```

Key zero-quotas to look for:

| Quota Code | Name | Notes |
|---|---|---|
| L-8528F119 | [bedrock-mantle] Input tokens/min Claude Opus 4.8 | Critical |
| L-37491D63 | [bedrock-mantle] Output tokens/min Claude Opus 4.8 | Critical |
| L-54814DC6 | [bedrock-mantle] Input tokens/min Claude Opus 4.7 | Critical |
| L-15CD18AC | [bedrock-mantle] Output tokens/min Claude Opus 4.7 | Critical |
| L-DB99DCDB | Cross-region tokens/min Claude Opus 4.8 | Also zero |
| L-15B8E632 | Cross-region tokens/min Claude Sonnet 4.6 | Also zero |
| L-58BE175A | Cross-region tokens/min Claude Haiku 4.5 | Also zero |

#### The Bug

The API reports `DesiredValue must be greater than the default quota value of 2.0E7` (20M tokens/min) even though the current value is 0. This is a known AWS bug where the `bedrock-mantle` endpoint overrides standard quotas to 0 but the API still sees the "real" default as 20M.

#### Fix: Request Quota Increase with Value > 20M

```python
import boto3

client = boto3.client('service-quotas', region_name='«secret:vault»')

quotas_to_fix = [
    ('L-8528F119', 'Input tokens/min Opus 4.8'),
    ('L-37491D63', 'Output tokens/min Opus 4.8'),
    ('L-54814DC6', 'Input tokens/min Opus 4.7'),
    ('L-15CD18AC', 'Output tokens/min Opus 4.7'),
]

for code, name in quotas_to_fix:
    try:
        r = client.request_service_quota_increase(
            ServiceCode='bedrock',
            QuotaCode=code,
            DesiredValue=20000001.0  # Must be > 20M (the phantom default)
        )
        status = r['RequestedQuota']['Status']
        print(f"✅ {name}: {status}")
    except Exception as e:
        if 'ResourceAlreadyExists' in str(e):
            print(f"⏭️  {name}: already requested")
        else:
            print(f"❌ {name}: {str(e)[:100]}")
```

Requests go to PENDING status. Approval is automatic for most accounts (minutes to hours).

#### Pitfall: Too Many Requests

Submitting quota increases for all 135 zero-quotas at once triggers `QuotaExceededException: This account has reached the maximum number of open service quota increase (SQI) requests`. Focus on the critical ones first (Opus/Fable input+output tokens/min), then batch the rest after approval. You **cannot submit new SQI requests** while existing ones are open — wait for them to resolve first. **Only request quotas for models you actually plan to use** — typically Opus 4.8 + Fable 5 input/output = 4 SQI max. Previous sessions submitted 19+ SQI for irrelevant models (Llama, Nova, Writer AI) which blocked all new requests for days.

#### Monitoring SQI Requests

Check status of all pending quota increase requests:

```bash
aws service-quotas list-requested-service-quota-change-history \
  --service-code bedrock --region «secret:vault» \
  --query 'RequestedQuotas[].[QuotaCode,QuotaName,Status,DesiredValue]' \
  --output table
```

Status values:
- `PENDING` — Queued, not yet reviewed
- `CASE_OPENED` — AWS Support case created (common for bedrock-mantle quotas on free-tier)
- `APPROVED` — Quota increased, model should work now
- `DENIED` — Request rejected

`CASE_OPENED` on free-tier accounts typically resolves in **24-72h** automatically. There is no way to accelerate this without a paid support plan.

#### Fable 5 zero-quota escalation

If Claude Fable 5 is `ACTIVE`, `get-foundation-model-availability` returns `AUTHORIZED` / `AVAILABLE`, and `us.anthropic.claude-fable-5` inference profile is `ACTIVE`, but invocation still fails with `AccessDeniedException: anthropic.claude-fable-5 is not available for this account`, check Fable-specific quotas before chasing IAM.

Known Fable 5 quota codes in `«secret:vault»`:
- `L-D06938E7` — Global cross-region model inference tokens per minute for Anthropic Claude Fable 5 — adjustable
- `L-9B258944` — Cross-region model inference tokens per minute for Anthropic Claude Fable 5 — adjustable
- `L-2775684C` — Global cross-region model inference tokens per day for Anthropic Claude Fable 5 — non-adjustable
- `L-23057DDF` — Model invocation max tokens per day for Anthropic Claude Fable 5 — non-adjustable

Action: request only the two adjustable token/min Fable 5 SQIs first with `DesiredValue=20000001.0`, then monitor for `CASE_OPENED`. The token/day quotas are non-adjustable and require AWS internal account eligibility/quota seeding. See `references/fable5-zero-quota-escalation.md` for the exact diagnosis pattern, quota codes, and support escalation template.

#### Automated Unlock Detection (Cron Pattern)

Set up a cron job to test Bedrock connectivity periodically and notify when quotas unlock:

```
# Prompt for cron job (every 2h):
"Test Bedrock: invoke Haiku 4.5 via aws bedrock-runtime invoke-model.
If success → report 'Bedrock LIVE' and test Opus/Fable.
If ThrottlingException → silent (no notification)."
```

This avoids manual checking. The cron fires silently until the first success, then notifies.

#### If API Requests Don't Approve

The `bedrock-mantle` quotas sometimes require an **AWS Support ticket**. Three free escalation paths, in order of effectiveness:

**Option A — Escalate Existing SQI Cases (BEST, free, works on Basic Support)**:
SQI requests in `CASE_OPENED` status create **real AWS Support cases**. You can add follow-up communications to these cases even on Basic Support (which blocks creating NEW technical cases). This is the fastest escalation path because the case already exists and is assigned to the quota team.

1. List SQI case IDs: `aws service-quotas list-requested-service-quota-change-history --service-code bedrock` then look for `CASE_OPENED` status
2. Find the `CaseId` field in the SQI response (15-digit number like `178127109000528`)
3. Navigate to case: `https://support.console.aws.amazon.com/support/home#/case/?displayId=CASE_ID`
4. The case detail page has a simple textarea + **Submit** button for adding communications
5. Fill textarea with urgency message (see template below), click Submit
6. Repeat for each relevant case

**Why this works**: Basic Support blocks creating NEW cases via the UI/API, but adding communications to EXISTING cases (created by the SQI system) is always allowed. The SQI-generated cases are already routed to the Bedrock quota team.

**Textarea template**:
```
URGENT: All bedrock-mantle quota requests have been in CASE_OPENED status for over 48 hours with no resolution. All Anthropic Claude models remain completely blocked with AccessDeniedException errors. EULA accepted, use case form submitted. Account [ACCOUNT_ID] has promotional credits that cannot be used. Please expedite.
```

**Camoufox automation for case communication** (the textarea is simple, unlike the creation form):
```python
# After login (use ~/.hermes/bin/aws-auto-login for full auto-login with Bitwarden MFA):
#   TAB=$(~/.hermes/bin/aws-auto-login --url "https://support.console.aws.amazon.com/support/home#/case/?displayId=CASE_ID")
# Or manual:
#   requests.post(f"{BASE}/tab/navigate", json={"tabId": TAB, "url": "https://support.console.aws.amazon.com/support/home#/case/?displayId=CASE_ID"})
time.sleep(6)

# Fill textarea (ID changes per page load - find dynamically)
eval_js("""
(function(){
    var ta = document.querySelector('textarea');
    if(!ta) return 'no textarea';
    var setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
    setter.call(ta, 'YOUR MESSAGE HERE');
    ta.dispatchEvent(new Event('input',{bubbles:true}));
    return 'set: ' + ta.value.length + ' chars';
})()
""")

# Click Submit
eval_js("(function(){var b=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='Submit');if(b){b.click();return'submitted';}return'no btn';})()")
```

Full automation recipe: `references/sqi-case-escalation.md`.

**Option B — New Billing Support Case (free)**:
Open a **Billing** support case (not Technical - that requires a paid plan). Full template and Camoufox automation recipe: `references/billing-support-case-template.md`. Note: Basic Support routes through Amazon Q chatbot first - type your issue, wait for Q investigation (20-30s), then click "Create a case" button. The AWS Support form React dropdowns (Service, Category, Severity) are extremely slow in Camoufox (25-30s timeouts per dropdown).

**Option C — AWS re:Post (free)**:
URL: https://repost.aws/questions/

### Section 7c: Claude Platform on AWS (Correct SaaS Registration Flow)

The Marketplace "Set up your account" button redirects to Bedrock home (broken as of 2026-06). The **correct flow** per AWS docs is:

1. Go to AWS Console → search for **"Claude Platform"** in the top bar
2. Click the **"Claude Platform on AWS"** service page
3. Click **"Get started"** (NOT "Set up your account" from Marketplace)
4. **"Review the terms and conditions"** modal appears → click **"Continue"**
5. AWS redirects to Anthropic's SaaS registration page (console.anthropic.com or platform.anthropic.com)
6. **Authenticate with Anthropic** — email + 6-digit verification code sent to that email (code expires in ~60s, see camoufox-automation `references/aws-mfa-resend-code-pitfall.md` for fast MFA pattern)
7. If "Signed in as a different account" appears → Log out and continue with the correct email
8. After sign-up, a default workspace is provisioned

**Source**: https://docs.aws.amazon.com/claude-platform/latest/userguide/setup.html

Key differences from Marketplace flow:
- Marketplace "Set up your account" → BROKEN (redirects to Bedrock home)
- "Claude Platform on AWS" → "Get started" → WORKS (official Anthropic flow)
- This provisions a NEW Anthropic organization tied to your AWS account (separate from existing Anthropic orgs)

**Troubleshooting**:
- "Setup failed: AWS account registration is incomplete or revoked" → Anthropic account is on the **Free Plan**. Must upgrade to paid plan first via `console.anthropic.com/settings/billing` (minimum $5 credit). See pitfall #19 below.
- "Sign-up failed: Failed to enable OutboundWebIdentityFederation" → Click Continue again
- "Signed in as a different account" → Log out and continue
- "Not found" during sign-in → Normal, appears briefly during redirect
- Verification codes expire in ~60 seconds — pre-enter email+password BEFORE asking for code. Use shift+mousedown pattern to resend if expired.
- **Stripe payment iframe limitation** — The Stripe credit card form is embedded in a cross-origin `<iframe>` that Camoufox cannot access. Use the webtop Chromium browser (Selkies port 3001) for manual payment. See `references/anthropic-console-billing-gate.md` for details.

### Bearer Token Auth (Alternative)

AWS Bedrock also supports bearer token auth via `Authorization: Bearer` header. Useful when you have a Claude Platform on AWS API key. See `references/bedrock-bearer-token-auth.md` for full details and model access comparison.

### Testing Strategy: Start with Haiku

Always test Bedrock connectivity with Haiku first (cheapest model at $1/$5 per MTok). Don't burn credits on Opus/Fable just to verify the endpoint works.

```bash
# Cheapest test — Haiku 4.5
python3 -c "
import boto3, json
c = boto3.client('bedrock-runtime', region_name='«secret:vault»')
r = c.converse(
    modelId='anthropic.claude-haiku-4-5-20251001-v1:0',
    messages=[{'role':'user','content':[{'text':'Say OK'}]}],
    inferenceConfig={'maxTokens':10,'temperature':0}
)
print(r['output']['message']['content'][0]['text'])
"
```

If this returns `OK`, the model is enabled. If ThrottlingException, wait 24h.

---

## Browser Automation and Console Setup

The former `aws-bedrock-browser-setup` skill is absorbed here as the browser-automation branch of Bedrock provisioning. Use it when CLI/IAM API access is not enough and the work must pass through AWS Console, Anthropic Console, Marketplace SaaS registration, or support/re:Post forms.

Key operational rules:
- Start from this Bedrock skill for the account/model/quota diagnosis, then load `camoufox-max-server` only for the browser mechanics.
- Prefer IAM user + least-privilege Bedrock permissions over root credentials after bootstrap.
- For AWS/Anthropic console flows, preserve the browser session between password, email code, MFA, and billing steps; restarting Camoufox invalidates short-lived codes and magic links.
- Use React native value setters and coordinate/keyboard endpoints for AWSUI, Clerk, and Stripe iframe interactions; plain `.value = ...` and DOM-only clicks frequently appear to work while React state remains empty.
- The archived source package keeps the detailed Camoufox recipes and references for AWS cookies, Anthropic console login, Stripe Link via Beeper, and AWS-specific Camoufox patterns.

## Pitfalls (All Sections)

1. Both config sections required — `bedrock.region` AND `providers.bedrock`.
2. Credentials in env file, not config.yaml — `key_env` is the var NAME.
3. Gateway restart required after config changes.
4. Long context (>200K tokens) = 2x pricing.
5. US-only inference (Opus 4.6+) adds 1.1x multiplier.
6. No free models — cheapest is Nova Micro at $0.035/MTok.
7. IAM user preferred over root for API access.
8. **Models must be enabled in console before invocation** — `ACTIVE` status in `list-foundation-models` does NOT mean invocable. Anthropic models require BOTH EULA agreement (API) AND use case form (console). See Section 7.
9. **`ConverseStream` vs `invoke-model`** — Both require model access activation. The error message differs slightly but the fix is the same (console enable).
10. **Hermes strips inference profile prefix** — Even if you configure `us.anthropic.claude-opus-4-8` in the models list, Hermes sends `anthropic.claude-opus-4-8` to the API. The prefix doesn't help; model access must be enabled regardless.
11. **ThrottlingException on new accounts** — Default daily token quota for free tier. Resets every 24h. Not an activation error — model IS accessible, just rate-limited.
12. **Model access page retired** — The old `#/modelaccess` page redirects to model catalog. Use case form is now triggered from the catalog page's yellow banner.
13. **Quotas stuck at zero** — New free-tier accounts have 100+ quotas at 0 on `bedrock-mantle` endpoint. Models appear ACTIVE and enabled but return ThrottlingException with zero usage. Fix: request quota increase with `DesiredValue=20000001.0` (>20M phantom default). See Section 7b.
14. **ThrottlingException can mean quota=0, not just rate limit** — On new accounts, "Too many tokens per day" with zero usage = quota stuck at 0, not a daily limit reached. Check quotas before waiting 24h.
15. **Use case form fields** — Company name, URL, industry dropdown (custom AWS UI component — needs `mousedown`+`click` dispatch, not just `.click()`), intended users checkboxes, use case description (500 char max). Industry dropdown uses `aria-haspopup="listbox"` + `aria-expanded` pattern.
16. **AccessDeniedException on newer models = zero quotas** — Opus 4.7/4.8, Fable 5, Haiku 4.5 return `AccessDeniedException` (NOT `ThrottlingException`) when bedrock-mantle quotas are at 0. Same root cause as #14, misleading error message. Don't chase EULA/Marketplace when it's the quotas. See `references/model-access-troubleshooting.md` §"Quota-Driven" table.
17. **SQI CASE_OPENED = 24-72h wait on free-tier** — Free-tier accounts without Premium Support get `CASE_OPENED` status on SQI requests. No way to accelerate. The cron watchdog pattern detects approval automatically.
18. **Marketplace "Set up your account" button is BROKEN for Anthropic products** — The Marketplace subscription page shows a "Set up your account" button for Anthropic products (e.g. "Claude Fable 5 (Amazon Bedrock Edition)"). As of 2026-06, this button **redirects to the Bedrock home page** instead of Anthropic's SaaS registration. The redirect loop happens because the browser needs to be pre-authenticated to Anthropic, but the flow doesn't enforce it. **Workaround**: Use the **"Claude Platform on AWS"** service page instead (see Section 7c). Agreement IDs look like `agmt-XXXXX` for product `prod-h6swdfybvty7y`. See `references/anthropic-marketplace-saas-registration.md` for the full flow.
19. **Anthropic Console billing gate blocks Marketplace SaaS** — Even with the correct "Claude Platform on AWS" flow, accounts on the Anthropic **Free Plan** cannot consume paid Marketplace offers. The console redirects to a pricing/plan selection page. Fix: upgrade via `console.anthropic.com/settings/billing` BEFORE retrying SaaS sign-up. **OTP verification is automatable** — enter email via Camoufox, ask user for the 6-digit code, enter it, then navigate to billing. Clerk SPA renders properly in Camoufox. Minimum credit purchase: $5. See `references/anthropic-console-billing-gate.md` for the full flow and Camoufox automation patterns.
19b. **Stripe payment iframe limitation** — The Stripe credit card form on Anthropic's billing page is embedded in a cross-origin `<iframe>`. Camoufox's `/tab/evaluate` cannot access iframe contents. Use the webtop Chromium browser (Selkies port 3001) for manual payment. Stripe Link verification codes are sent to Beeper chat "stripelink". See `references/anthropic-console-billing-gate.md` for the full workaround.
19c. **Two-account strategy for free-plan bypass** — If the primary AWS-linked Anthropic account (earndeel@gmail.com) is on the Free Plan and cannot upgrade, use a secondary paid Anthropic account (lucas.jouvencon@gmail.com, $1.74 balance) to complete the SaaS sign-up. The secondary account must have billing enabled. Flow: log into Anthropic Console with secondary account → navigate to Claude Platform on AWS → sign up with AWS credentials. The SaaS subscription binds to the Anthropic org, not the AWS account, so the secondary account's paid status satisfies the billing gate.
19d. **AWS root MFA IS in Bitwarden (after sync)** — The earndeel@gmail.com AWS root login TOTP exists in Bitwarden (item `e790ded6`, signin.aws.amazon.com). It was invisible until `bw sync` ran. Use `~/.hermes/bin/aws-mfa` to get the current 6-digit code, or `~/.hermes/bin/aws-auto-login` for full automated login (email → password → MFA → console). Always `bw-unlock --sync` before TOTP retrieval. MFA code can be asked from user as fallback.
20. **Bedrock model IDs ≠ Anthropic direct API IDs** — Anthropic's API uses date-suffixed IDs like `claude-opus-4-8-20260213`, but Bedrock uses shorter IDs like `anthropic.claude-opus-4-8` (no date suffix). Using Anthropic-format IDs on Bedrock returns `ValidationException: The provided model identifier is invalid`. Always discover IDs via `list-foundation-models` or `list-inference-profiles` — don't copy IDs from Anthropic's model docs. For `invoke-model` CLI, use inference profile IDs (`us.anthropic.claude-opus-4-8`) not foundation model IDs.
21. **Bearer token auth exists but doesn't unlock models** — AWS Bedrock supports `Authorization: Bearer` header with `ABS`-prefix tokens (from Claude Platform on AWS). Works for authentication but gives identical 403 errors as IAM credentials for blocked models. Haiku 4.5 and Sonnet 4.6 work; Opus 4.8 and Fable 5 remain blocked at the account level. Hermes Bedrock provider uses IAM (SigV4), not bearer token. See `references/bedrock-bearer-token-auth.md`.
19. **OpenRouter fallback for Bedrock-blocked models** — When `bedrock-mantle` quotas are stuck at 0 (new free-tier accounts), all Anthropic models (Opus 4.8, Fable 5, Sonnet 4.6, Haiku 4.5) are available on OpenRouter at the **same per-token pricing** as Bedrock. Use `openrouter` provider in Hermes with `anthropic/claude-opus-4.8` or `anthropic/claude-fable-5` model IDs. No use case form, no quotas, no SQI requests needed. Tested and confirmed working (2026-06). This is the fastest path to production while waiting for Bedrock SQI approval (24-72h). Note: OpenRouter also offers "fast" variants (e.g., `anthropic/claude-opus-4.8:fast`) at 2x price ($10/$50) for higher throughput.
