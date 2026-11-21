---
name: scena-serverless-deploy-workflow
description: Use when building, operating, or debugging Scena requires Cloudflare serverless deployment, especially when Wrangler fetch failures in sandbox or CI require a curl deployment fallback.
type: workflow
requires: [scena-video-factory, scena-cloudflare-serverless, cloudflare-worker-deploy-curl]
---

# Scena Serverless Deployment Workflow

## Scope and order

Orchestrate the existing skills; do not replace their implementation instructions. Follow this order: product and engine diagnosis → serverless integration and deployment → conditional curl fallback → verification. The full three-skill chain applies when Scena work requires a Worker release and Wrangler cannot reach Cloudflare because of a fetch/network failure. If normal deployment succeeds, skip the fallback.

## 1. Establish the Scena change contract

load scena-video-factory with skill_read.

Use its relevant references to diagnose the request and identify the smallest engine, provider, workflow, or SaaS change. Gather runtime evidence before choosing a fix.

**Hand off to step 2:** repository and revision, affected tenant and flow, diagnostic evidence, proposed changes, API/provider contracts, configuration dependencies, required tests, and acceptance criteria. Include identifiers and redacted evidence, not credentials.

**Gate:** Confirm whether the affected path is chat-agent, SaaS pipeline, or both. Identify tenant-isolation, existing-chat compatibility, and provider-routing risks. Do not advance with an assumed root cause or unresolved contract ambiguity.

## 2. Prepare and attempt the serverless release

load scena-cloudflare-serverless with skill_read.

Read the deployment reference and the runtime, provider, Telegram, Pages, or pipeline references relevant to the change contract. Use this skill to implement and validate the Cloudflare integration and prepare the release. Resolve contradictory or historical instructions against current repository configuration and verified runtime evidence; do not silently change model routing, credentials, or deployment targets.

**Checks before deployment:** Confirm the intended account, Worker, environment, routes, bindings, live schema compatibility, and any Pages target. Confirm applicable regression tests pass and that affected approval gates, tenant routing, callbacks, and chat/SaaS state boundaries remain correct. Use the current credential procedure from the deployment skill; never carry credentials in the handoff.

Attempt the normal supported deployment. If it succeeds, proceed to completion checks. If it fails, classify the failure before retrying.

**Hand off to step 3 only for a Wrangler fetch/network failure:** exact redacted error, repository revision, build/config paths, intended account and Worker identifiers, environment, required bindings and compatibility settings, migration status, test results, and outstanding Pages or routing work.

**Gate:** Authentication, compilation, migration, configuration, or application failures are not reasons to bypass Wrangler with curl. Resolve those failures in their owning step first.

## 3. Deploy through the conditional curl fallback

load cloudflare-worker-deploy-curl with skill_read.

Follow that skill for credential resolution, bundling, REST upload, and initial verification. Do not reconstruct its commands or upload format from memory. Preserve the exact release target and deployment configuration handed over by step 2.

**Checks:** Confirm the bundle represents the tested revision and intended environment; verify required metadata and bindings are preserved. Require an explicitly successful Cloudflare response and live endpoint verification. A successful upload alone is not proof that the application works.

**Return to step 2 for integration verification:** deployment result, deployed version identifier when available, redacted API response, health-check evidence, and any remaining Pages, route, migration, or configuration tasks. The Worker upload does not complete those tasks automatically.

## Completion and failure handling

Verify the deployed health endpoints and the affected user/API flow against step 1's acceptance criteria. Check runtime logs and durable state, including asynchronous completion where relevant. Confirm required frontend releases and routing separately.

If verification fails, return to step 1 for engine/provider issues or step 2 for serverless integration issues; do not repeatedly redeploy without new evidence. Stop and report blockers when target identity, credentials, schema safety, or configuration conflicts cannot be resolved.

Report the change, test results, deployment method and version, live verification evidence, and remaining risks. Distinguish tested behavior from unverified assumptions; never claim completion based solely on an upload response.
