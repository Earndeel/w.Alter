# Anthropic Marketplace SaaS Registration (Fable 5 / Opus 4.8)

## ⚠️ CRITICAL: Marketplace "Set up your account" Button Is Broken (2026-06)

The "Set up your account" button on the Marketplace/Subscriptions page **redirects to the Bedrock home page** instead of Anthropic's SaaS registration. This is a known issue observed on multiple browsers and accounts.

**Use the "Claude Platform on AWS" service page instead** (see "Correct Flow" below).

## When This Is Needed

After accepting the AWS Marketplace agreement for Anthropic models (Fable 5, Opus 4.8+), the SaaS registration step must be completed. This links your AWS account to Anthropic's platform.

## Symptoms of Incomplete Registration

- Marketplace shows agreement accepted (status `ACTIVE`)
- "Set up your account" button still visible
- Bedrock invocation returns `AccessDeniedException` even with EULA + use case form completed
- Quotas may still be at 0 (bedrock-mantle endpoint)

## Correct Flow: Claude Platform on AWS (2026-06)

Per official AWS docs (https://docs.aws.amazon.com/claude-platform/latest/userguide/setup.html):

### Step 1: Open Claude Platform on AWS
- Go to AWS Console → search for **"Claude Platform"** in the top bar
- Click the **"Claude Platform on AWS"** service page

### Step 2: Sign Up
- Click **"Sign up"** (NOT "Set up your account" from Marketplace)
- If you have a private offer, contact your Anthropic/AWS account exec first

### Step 3: Wait for Provisioning
- Sign-up takes a few minutes
- AWS handles the Marketplace subscription automatically
- Page shows "Sign-up in progress" banner (no progress bar)
- Stay on the page — don't refresh

### Step 4: Anthropic Organization Setup
- After sign-up, you're redirected to platform.anthropic.com
- If "Signed in as a different account" → Log out and continue with your email
- A default workspace is provisioned automatically

### Step 5: Note Your Workspace ID
- The workspace ID is needed for API access

### Step 6: Sign in to Claude Console
- Access is federated through AWS IAM
- Assume an IAM role with `aws-external-anthropic:AssumeConsole` permission
- AWS Console issues a JWT and redirects to platform.anthropic.com
- "Account managed by AWS" indicator appears in sidebar

## Old Flow (BROKEN — Marketplace Subscriptions)

The old flow via Marketplace → "Set up your account" no longer works (2026-06):

1. ~~Navigate to https://us-east-1.console.aws.amazon.com/home#/subscriptions~~
2. ~~Find Anthropic product → Click "Set up your account"~~
3. ~~Redirects to https://platform.claude.com/partner-signup?redirect_url=...~~

This redirect now bounces to Bedrock home instead of Anthropic.

## Troubleshooting

- **"Sign-up failed: Failed to enable OutboundWebIdentityFederation"** → Click Continue again
- **"Signed in as a different account"** → Log out and continue
- **"Not found" during sign-in** → Normal, appears briefly during redirect
- **Code expiry (~90s)** — If email verification is needed, have the email ready before requesting code
- **Each "Resend code" invalidates ALL previous codes**

## Key Details

- Product ID: Fable 5 = `prod-h6swdfybvty7y`
- Agreement ID format: `agmt-XXXXX`
- This provisions a NEW Anthropic organization tied to your AWS account
- Separate from existing Anthropic orgs (including Claude Enterprise)
- Discounts from private offers cannot be applied retroactively
