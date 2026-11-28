---
name: scena-worker-curl-release
description: Use when a Scena V2 change requires a Cloudflare Worker release and Wrangler deployment fails with a networking or fetch error, or the execution environment requires curl deployment.
type: workflow
requires: [scena-cloudflare-serverless, cloudflare-worker-deploy-curl]
---

# Scena Worker curl release

## When this chain applies

Use this workflow to carry a Scena change from application-specific preparation through the curl deployment fallback and back to application verification. If normal Wrangler deployment works, finish through the Scena skill; do not invoke the fallback solely because it is available. Pages-only releases do not need this chain.

## 1. Prepare the Scena release

load scena-cloudflare-serverless with skill_read.

Read its deployment reference and only the additional references relevant to the changed behavior. Follow those instructions to prepare the change, validate it, and identify any required schema, configuration, secrets, or companion-service prerequisites.

Hand off a release manifest containing the source revision, working directory, Worker configuration and environment, intended account and script identity, required bindings and compatibility settings, prerequisite status, affected routes, and expected verification outcomes. Include the observed Wrangler networking failure or the environment constraint requiring curl. Pass credential references or the authorized injection mechanism, never credential values.

**Gate:** Confirm that prerequisites and applicable checks succeeded and that the fallback addresses a transport problem. Compilation, authentication, schema, or application failures must be resolved before upload; curl is not a remedy for them. Verify the actual deployment target and public routing rather than inferring them from a domain name.

## 2. Deploy the prepared Worker through curl

load cloudflare-worker-deploy-curl with skill_read.

Use its credential, bundling, and REST upload procedure against the exact configuration and target in the release manifest. Keep Scena-specific requirements from step 1 in force. Do not recreate deployment commands or multipart handling in this workflow.

**Before upload:** Check that the generated artifact corresponds to the prepared revision and environment, and that its metadata preserves the required bindings and settings. Resolve conflicting authentication guidance using the supported credential helper and live checks without exposing secrets; do not guess credentials or broaden access to overcome a failure.

Hand off the upload result, deployed version or identifier when available, target identity, artifact provenance, and initial health-check result.

**Gate:** Require an explicitly successful Cloudflare API result. After an ambiguous timeout, inspect deployment state before retrying. Stop on a definitive failure; do not report a release as successful or repeatedly upload without diagnosis.

## 3. Verify Scena behavior

load scena-cloudflare-serverless with skill_read.

Use the release manifest and deployment receipt to run its applicable post-deployment checks, including checks for the changed Telegram, media, pipeline, or frontend behavior. Verify the intended public route reaches the deployed Worker. Carry out functional checks within the authorized scope; deployment alone does not authorize production generation.

**Completion:** Report the deployed target and version, checks performed and their outcomes, and any unresolved failures. API upload success is an intermediate result; complete the release only after the relevant Scena checks pass. If verification fails, retain the deployment receipt and return the failure to Scena diagnosis before preparing another release.
