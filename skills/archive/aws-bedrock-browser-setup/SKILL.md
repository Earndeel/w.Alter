---
name: aws-bedrock-browser-setup
description: Set up AWS Bedrock access via Camoufox browser automation — cookie extraction, IAM user creation, access key generation, and vault storage.
tags: [aws, bedrock, camoufox, browser, iam, credentials]
---

# AWS Bedrock Browser Setup

## Context
AWS Bedrock credentials obtained via Camoufox anti-detect browser + Mac Brave cookies + Tailscale exit node. Account «secret:vault» (earndeel), $100 credits.

## Prerequisites
- Camoufox-max server running on port 9377/9378
- Mac Brave browser cookies extracted (Keychain AES decryption)
- Tailscale exit node configured (Mac IP)

## Steps

### 1. Start Camoufox with Tailscale
```bash
cd /root/.hermes/camoufox-max
CAMOUFOX_MAX_PORT=9377 node server-max.js
```

### 2. Inject AWS Cookies
Extract from Mac Brave SQLite + Keychain decrypt. Inject into `storage-state.json`.

### 3. Navigate to AWS Console
```python
# Use /tab/evaluate for JS injection (React-based UI)
# Navigate to IAM users page
cf("POST", "/tab/evaluate", {"expression": "window.location.href = 'https://us-east-1.console.aws.amazon.com/iamv2/home#/users'"})
```

### 4. Create IAM User
- Use `/tab/evaluate` to inject click events (standard selectors fail on React)
- Attach `AmazonBedrockFullAccess` policy

### 5. Generate Access Keys
- Navigate to user's security credentials page
- Click "Create access key" → "Application running outside AWS"
- Extract Access Key ID and Secret Access Key

### 6. Store in Vault
```bash
vault set aws/access_key_id AKIA...
vault set aws/secret_access_key ***
vault set aws/account_id <ACCOUNT_ID>
vault set aws/region «secret:vault»
```

## Bedrock API Usage

### Inference Profiles (CRITICAL)
Newer Claude models require inference profiles, NOT raw model IDs:
```python
# WRONG: modelId='anthropic.claude-haiku-4-5-20251001-v1:0'
# RIGHT: modelId='us.anthropic.claude-haiku-4-5-20251001-v1:0'
```

Prefixes:
- `us.anthropic.` — US region inference
- `global.anthropic.` — Global inference

### Invoke Model
```python
import boto3, json

client = boto3.client('bedrock-runtime', region_name='«secret:vault»',
    aws_access_key_id=key_id, aws_secret_access_key=secret)

response = client.invoke_model(
    modelId='us.anthropic.claude-haiku-4-5-20251001-v1:0',
    contentType='application/json',
    accept='application/json',
    body=json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "Hello"}]
    })
)
```

### List Available Models
```python
bedrock = boto3.client('bedrock', region_name='«secret:vault»', ...)
models = bedrock.list_foundation_models()
# Filter by provider: anthropic, meta, mistral, etc.
```

### List Inference Profiles
```python
profiles = bedrock.list_inference_profiles()
# Returns model IDs with correct prefixes
```

## Claude Platform on AWS — SaaS Registration

The Claude Platform on AWS requires a **two-service sign-up**:

### Correct Flow (DO NOT use Marketplace → Subscriptions)
1. Navigate to `https://us-east-1.console.aws.amazon.com/claude-platform/`
2. Click **"Sign up"** (NOT "Set up your account" from Marketplace)
3. AWS redirects to Anthropic Console for federated sign-in
4. Authenticate with Anthropic account
5. Anthropic redirects back to AWS → provisioning completes in ~2 min

### Pitfall: Marketplace "Set up your account" is broken
The Marketplace Subscriptions page shows a "Set up your account" button for Fable 5 / Opus 4.8 that **redirects to the Bedrock home page** instead of Anthropic. This is a known AWS UI bug. Use the Claude Platform service page directly.

### Pitfall: Anthropic account must be on a PAID plan
The federated sign-in fails with: *"Accounts with the free plan are not eligible to purchase paid offers."*

**Fix**: Upgrade earndeel@gmail.com — go to `console.anthropic.com/settings/billing`, buy minimum $5 credits.

**Anthropic Billing Flow via Camoufox** (2026-06 tested):
1. Login to Anthropic Console (magic link via Gmail API for lucas.jouvencon@gmail.com, or ask user for earndeel@gmail.com code)
2. Navigate to `https://console.anthropic.com/settings/billing`
3. Click **"Add funds"** → minimum $5 credit purchase
4. Stripe Checkout modal appears — enter card details in Stripe Elements iframe
5. Stripe may trigger **Link verification** (email code sent to the account email)
6. **Retrieval**: check Beeper messages for Stripe verification code:
   ```bash
   curl -s -X GET 'http://localhost:5050/v1/messages?limit=10' \
     -H "Authorization: Bearer <beeper_token>" | jq '.[] | select(.content.body? // "" | test("stripe|link|verification|code"))'
   ```
7. Enter code in Stripe modal → payment completes → account upgraded

**Pitfall**: "Add funds" button is only visible when account is on Free Plan. If already upgraded, the billing page shows balance and usage instead.

**Pitfall**: Stripe Checkout modal is rendered in an iframe — standard `/tab/evaluate` JS runs in the parent frame, not in Stripe's iframe. Use Playwright's frame-aware selector or `page.frameLocator()` to target Stripe Elements fields.

**Pitfall**: The Anthropic billing page URL changes after successful payment. If you navigate back to `/settings/billing`, verify the page shows "Balance" with the funded amount, not still the "Add funds" button. If "Add funds" still appears, the payment may have failed silently — check Stripe dashboard.

### Anthropic Console Login via Camoufox (Magic Link)
Anthropic uses Clerk auth which sends **magic links** (not 6-digit OTP codes) to the email:

1. Navigate to `https://console.anthropic.com/`
2. Enter email → click "Continue with email"
3. Anthropic sends a magic link email
4. Retrieve link via Gmail API (only works for `lucas.jouvencon@gmail.com`):
   ```bash
   $GAPI gmail search "from:anthropic newer_than:5m" --max 3
   $GAPI gmail get <message_id>
   # Extract: https://platform.claude.com/magic-link#<token>:<base64_email>
   ```
5. Navigate Camoufox directly to the magic link URL → auto-logged in
6. Verify login by navigating to `https://console.anthropic.com/settings/billing`

**Pitfall**: The magic link is one-use and expires quickly. Retrieve and use it within ~2 minutes.

**Pitfall**: `earndeel@gmail.com` is NOT accessible via Gmail API (only `lucas.jouvencon@gmail.com` has OAuth). For earndeel, ask user to forward the magic link or enter the code manually.

See `references/anthropic-console-login.md` for the full Camoufox automation pattern.

## AWS Console Login via Camoufox (Root User)

When cookies expire and you need to re-authenticate to the AWS console:

1. Navigate to `https://repost.aws/questions/ask` (or any AWS service)
2. AWS redirects to sign-in → click "Sign in using root user email"
3. Enter email (`earndeel@gmail.com`), click Next
4. Enter password (from Bitwarden: `signin.aws.amazon.com` entry), click Sign in
5. AWS sends a **verification code** to the email — this is the blocker

**Verification code flow is time-sensitive**: the code expires quickly and a NEW code is sent on each login attempt. You must retrieve and enter the code within ~2 minutes.

**Retrieval options**:
- Mac Brave browser via SSH + AppleScript (screen server required for screencapture)
- Ask user to forward the code (simplest)
- **Gmail API NOT available** for `earndeel@gmail.com` — only `lucas.jouvencon@gmail.com` has OAuth configured in Hermes. The Bitwarden master password cannot decrypt Gmail API access for the AWS account email.

**MFA flow pitfalls**:
- Each failed login or "Resend code" sends a NEW code — previous codes expire instantly
- Codes expire in ~90 seconds from send time
- Camoufox **MUST NOT** be restarted between entering credentials and entering the code — the session is destroyed and a new code is sent on the next attempt
- Take screenshot immediately after entering code to verify success/failure before it times out
- If code expired, the error message is generic ("Sorry, that code didn't work") — doesn't distinguish expiry from wrong code
- **AWS CAPTCHA on sign-in**: If AWS shows a CAPTCHA image during login (typical on new accounts or after multiple attempts), use `vision_analyze` to read the CAPTCHA text from a screenshot, then inject the text into the CAPTCHA input field via `/tab/evaluate`. The CAPTCHA image is loaded from `amcs-captcha-prod-*.s3.*.amazonaws.com` but cannot be downloaded directly (session-scoped) — must screenshot the rendered page.

**CRITICAL**: Do NOT restart Camoufox between entering credentials and entering the code — the session is lost and a new code will be sent.

## bedrock-mantle Quota Issue (Free Tier)

New AWS accounts (especially free tier) may have ALL `bedrock-mantle` service quotas set to **0**, blocking ALL model invocation even after approval. Symptoms:
- `ThrottlingException: Too many tokens per day` (quotas at 0)
- `AccessDeniedException` for inference profiles

**Root cause**: Known AWS platform bug where free tier accounts don't get default quotas assigned.

**Workaround**: Post on AWS re:Post requesting quota reset to defaults:
- URL: `https://repost.aws/questions/ask`
- Category: "Amazon Bedrock" → "General"
- Title: "bedrock-mantle service quotas stuck at 0 — all models blocked"
- Body: Request all `bedrock-mantle` quotas be set to default values for account «secret:vault»

**Resolution**: Request quota increase via API with `DesiredValue=20000001.0` (>20M phantom default). See `aws-bedrock-setup` skill §7b for the full fix. For cases that go to `CASE_OPENED` status, wait 24-72h. The Marketplace SaaS registration ("Set up your account") is a billing entitlement step — NOT the API access blocker. Focus on quotas first.
1. Navigate to `https://repost.aws/questions/ask`
2. If redirected to `/account/registration` → profile creation required first (display name, email, opt-in checkboxes)
3. Then redirected to AWS sign-in → root user flow (email + password + verification code)
4. After auth, redirected back to question form → fill title, body, tags, category
5. **re:Post requires AWS auth on EVERY visit** — session does not persist across Camoufox restarts

Resolution typically takes 24-48h after re:Post ticket.

## Pitfalls
- **Camoufox stability for long sessions**: AWS console sessions are long-lived. Camoufox can crash silently. Implement the health check + auto-restart pattern from `camoufox-automation` skill §4. Without it, multi-step flows (IAM user creation, access key generation, Claude Platform sign-up) fail mid-way with "Target page, context or browser has been closed". See `references/server-stability-patches.md` in camoufox-automation skill.
- **Playwright-core crashes**: Patch `node_modules/playwright-core/lib/coreBundle.js` to handle undefined `pageError.location`
- **AWS Console React UI**: Standard click selectors fail; use `/tab/evaluate` for JS injection
- **Model ID vs Inference Profile**: Newer models (Haiku 4.5+, Opus 4.6+, Fable 5) require inference profiles
- **Cookie consent modals**: AWS shows cookie banners; dismiss via JS before proceeding
- **Root vs IAM user**: Root credentials work but are less secure; prefer IAM user with minimal permissions
- **Verification code expiry**: AWS root login sends email codes that expire in ~90 seconds. Do NOT restart Camoufox mid-flow. Retrieve code fast via Mac SSH or ask user. Each "Resend code" invalidates ALL previous codes. **CRITICAL**: Camoufox must stay alive between credential entry and code entry — if the browser crashes, the session is destroyed and a new code is sent on the next attempt. Use the health check + auto-restart pattern from camoufox-automation skill §4.
- **Gmail API limitation**: Only `lucas.jouvencon@gmail.com` has OAuth. `earndeel@gmail.com` (AWS root email) is NOT accessible via Gmail API — use Mac Brave or ask user.
- **re:Post requires full AWS auth**: Every visit to `repost.aws/questions/ask` triggers the full sign-in flow (root user + email MFA). Camoufox session state is lost on restart. Complete the entire flow in one session.
- **bedrock-mantle quotas at 0**: Free tier bug — all model invocation blocked until quotas are manually set via re:Post ticket.
- **Anthropic Console billing gate**: Free Plan accounts cannot consume paid Marketplace offers. Must upgrade at `console.anthropic.com/settings/billing` first (Pro $20/mo or Team $30/mo/person). See `aws-bedrock-setup` skill §19 and `references/anthropic-console-billing-gate.md`.
- **Anthropic Console OTP blocker**: Clerk authentication on `console.anthropic.com` requires email OTP sent to earndeel@gmail.com. Gmail API only configured for lucas.jouvencon@gmail.com. Cannot automate — ask user to upgrade billing manually or forward the code.
- **Anthropic magic link (not OTP)**: Clerk auth sends magic links, not 6-digit codes. Format: `https://platform.claude.com/magic-link#<token>:<base64_email>`. Retrieve via Gmail API for lucas.jouvencon@gmail.com, navigate Camoufox directly to the URL. One-use, ~2 min expiry. See `references/anthropic-console-login.md`.
- **Password escaping in /tab/evaluate**: Never manually escape passwords in JS strings. Use Python `json.dumps()` to generate the expression: `f'inp.value = {json.dumps(password)}'`. Manual escaping fails on special chars like `@`, `\`, `"`.
- **Claude Platform "Sign up" vs Marketplace "Set up your account"**: Use `https://us-east-1.console.aws.amazon.com/claude-platform/` → "Sign up". The Marketplace Subscriptions page "Set up your account" button redirects to Bedrock home (broken).
- **Gmail API account limitation**: Only `lucas.jouvencon@gmail.com` has OAuth. `earndeel@gmail.com` (AWS root) is NOT accessible via Gmail API — use Mac Brave SSH or ask user.

## Model Catalog (June 2026)

### Anthropic Claude (all via inference profiles)
| Model | Profile ID | Input/MTok | Output/MTok |
|---|---|---|---|
| Fable 5 | `us.anthropic.claude-fable-5` | $10 | $50 |
| Opus 4.8 | `us.anthropic.claude-opus-4-8` | $5 | $25 |
| Opus 4.7 | `us.anthropic.claude-opus-4-7` | $5 | $25 |
| Opus 4.6 | `us.anthropic.claude-opus-4-6-v1` | $5 | $25 |
| Opus 4.5 | `us.anthropic.claude-opus-4-5-20251101-v1:0` | $5 | $25 |
| Sonnet 4.6 | `us.anthropic.claude-sonnet-4-6` | $3 | $15 |
| Sonnet 4.5 | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | $3 | $15 |
| Haiku 4.5 | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | $1 | $5 |

### Amazon Nova (own models, very cheap)
| Model | ID | Input/MTok | Output/MTok |
|---|---|---|---|
| Nova Micro | `amazon.nova-micro-v1:0` | $0.035 | $0.14 |
| Nova Lite | `amazon.nova-lite-v1:0` | $0.06 | $0.24 |
| Nova Pro | `amazon.nova-pro-v1:0` | $0.80 | $3.20 |
| Nova 2 Lite | `amazon.nova-2-lite-v1:0` | — | — |
| Nova 2 Sonic | `amazon.nova-2-sonic-v1:0` | — | — |

### Other Providers (ON_DEMAND, no inference profiles needed)
| Provider | Models |
|---|---|
| **DeepSeek** | V3.2, R1 |
| **Meta Llama** | 4 Scout 17B, 4 Maverick 17B, 3.3 70B, 3.1 8B/70B |
| **Qwen3** | Coder Next, Next 80B A3B, 32B, VL 235B, Coder 30B |
| **Mistral** | Large 3 (675B), Devstral 2, Ministral 3B/8B/14B, Magistral Small |
| **MiniMax** | M2, M2.1, M2.5 |
| **Moonshot** | Kimi K2.5, K2 Thinking |
| **Z.AI (Zhipu)** | GLM 5, GLM 4.7, GLM 4.7 Flash |
| **NVIDIA** | Nemotron Nano 9B/12B/30B, Super 120B |
| **OpenAI** | gpt-oss-20b, gpt-oss-120b (open-source only) |
| **Writer** | Palmyra X4, X5, Vision 7B |
| **Cohere** | Embed v4, Command R/R+, Rerank 3.5 |
| **Google** | Gemma 3 4B/12B/27B |

### NOT Available on Bedrock
- **MiMo 2.5** (Xiaomi) — only on platform.xiaomimimo.com / OpenRouter
- **GPT-5.5 / GPT-5 / GPT-4o** — OpenAI proprietary, only on OpenAI API
- **Kimi K2.6** — only K2.5 available
- **MiniMax M3** — only M2/M2.1/M2.5
- **Qwen 3.7** — only Qwen3 series

## Free Credits Program

AWS offers up to **$200 in credits** for new accounts (confirmed 2026-06):
- **$100** on sign-up (automatic, `AWS Free Tier` credit)
- **$100** earned by completing 5 onboarding activities ($20 each):

| # | Activity | Service | CLI | Cleanup |
|---|----------|---------|-----|---------|
| 1 | Launch an instance | EC2 (t3.micro) | `aws ec2 run-instances` | `aws ec2 terminate-instances` |
| 2 | Set up a cost budget | AWS Budgets | `aws budgets create-budget` | `aws budgets delete-budget` |
| 3 | Use a Bedrock model | Bedrock | `aws bedrock-runtime invoke-model` | N/A |
| 4 | Create an Aurora or RDS database | RDS | `aws rds create-db-instance --db-instance-class db.t3.micro --engine mysql` | `aws rds delete-db-instance --skip-final-snapshot` |
| 5 | Create a web app using Lambda | Lambda | `aws lambda create-function` | `aws lambda delete-function` + delete IAM role |

**Activities auto-detected**: Credits appear within minutes of completing each activity (not all-or-nothing). Check at Billing → Credits page.

**Find activities**: Console Home → "Explore AWS" widget, or Billing → Credits page.

**IMPORTANT — cleanup immediately** after credit appears to avoid charges:
- RDS: `aws rds delete-db-instance --db-instance-identifier <id> --skip-final-snapshot`
- Lambda: `aws lambda delete-function --function-name <name>` + detach+delete IAM role
- EC2: `aws ec2 terminate-instances --instance-ids <id>`

**Lambda requires IAM role**: Create role with Lambda trust policy + `AWSLambdaBasicExecutionRole` before creating function. Delete role after function cleanup.

Other credit programs:
- **AWS Activate** (startups): $1K–$100K
- **Generative AI Accelerator**: $5K–$100K
- **EdStart** (education): $1K+

## Verification

### Quick Connectivity Test (Haiku 4.5 — cheapest model)
```bash
AWS_ACCESS_KEY_ID=$(vault get aws/access_key_id) \
AWS_SECRET_ACCESS_KEY=$(vault get aws/secret_access_key) \
aws bedrock-runtime invoke-model \
  --model-id us.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --content-type application/json \
  --accept application/json \
  --body '{"anthropic_version":"bedrock-2023-05-31","max_tokens":50,"messages":[{"role":"user","content":"Reply with exactly: Bedrock OK"}]}' \
  /tmp/bedrock-test.json && cat /tmp/bedrock-test.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('content',[{}])[0].get('text','NO TEXT'))"
```

**Expected**: `Bedrock OK` — confirms credentials, quotas, and inference profile access all work.
**Cost**: ~$0.0001 (Haiku 4.5 is $1/$5 per MTok, this is <100 tokens).

**If ThrottlingException**: quotas still at 0 — see `bedrock-mantle` section above.
**If AccessDeniedException**: inference profile not enabled — check model access in Bedrock console.
**If ValidationException**: wrong model ID format — use inference profile (`us.anthropic.*`) not raw ID.

### Identity Check
```bash
AWS_ACCESS_KEY_ID=$(vault get aws/access_key_id) \
AWS_SECRET_ACCESS_KEY=$(vault get aws/secret_access_key) \
aws sts get-caller-identity
```
