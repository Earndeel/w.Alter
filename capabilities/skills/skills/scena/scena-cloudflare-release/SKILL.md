---
name: scena-cloudflare-release
description: Use when releasing or repairing Scena across its Cloudflare Pages frontend and Worker backend, including curl deployment fallback when Wrangler cannot reach the Workers API.
type: workflow
requires: [scena-video-factory, cloudflare-pages-deploy, cloudflare-worker-deploy-curl]
---

# Scena Cloudflare Release

Orchestrate Scena implementation, Pages delivery, and conditional Worker deployment fallback. The sub-skills own implementation details and deployment commands; load them at the relevant step rather than reproducing their procedures here.

## When the chain applies

Use this workflow when a Scena change spans its static frontend and Worker backend, or when diagnosing an incomplete release across those surfaces. Follow the order below. Execute the curl fallback only when Worker deployment is required and Wrangler has a confirmed networking failure. A Pages-only change or a healthy Worker deployment does not require that fallback.

## 1. Establish and prepare the Scena release

Load scena-video-factory with skill_read.

Use its relevant references to inspect the live architecture, diagnose the issue, implement the requested changes, and run the required tests. Treat historical paths, provider choices, and deployment descriptions as discovery leads until verified against the current project.

Prepare a release handoff containing:
- Source revision, intended environment, and changed components.
- Verified Cloudflare account, Pages projects and domains, Worker identity and routes, and required bindings.
- Frontend build directory, API origins, and frontend/backend contract changes.
- Required migrations or configuration changes, test results, and recovery target.
- Worker deployment status: unnecessary, successful, or blocked, with the specific failure evidence.

Use the Scena skill's normal Worker deployment path when required. If Wrangler cannot reach the Workers API, retain the failure evidence and mark Worker publication pending for step 3.

**Gate:** Resolve failing tests and ambiguous deployment targets before proceeding. Establish whether the new frontend can operate with the currently live backend. If it cannot and Worker publication is pending, step 2 may prepare or deploy a preview, but must defer production promotion until step 3 succeeds.

## 2. Deliver the Pages frontend

Load cloudflare-pages-deploy with skill_read.

Consume the release handoff to discover the existing Pages project that owns the intended domain, validate the frontend artifact, and deploy through the sub-skill's procedure. Load its existing-project and production-verification references as needed.

Check that frontend API origins match the intended Worker environment. Verify the deployed artifact, static assets, and relevant frontend behavior at the deployment URL. Check the canonical domain separately; a successful upload or working preview alone does not establish production success.

Hand forward the Pages project, deployment identifier and URL, canonical domain, artifact revision, verification results, and any deferred production promotion. Carry forward the Worker target, bindings, contract requirements, and original Wrangler failure evidence from step 1.

**Gate:** Investigate Pages deployment or verification failures through the Pages skill. The Worker curl fallback does not repair a Pages upload failure. Proceed to step 3 only for a required Worker publication blocked by Wrangler networking; otherwise continue to final verification.

## 3. Publish the Worker through the conditional fallback

Load cloudflare-worker-deploy-curl with skill_read.

Use the same release revision, verified Worker identity, environment, bindings, and routes from the handoff. Follow the sub-skill's credential resolution, bundling, upload, and verification procedure. Confirm the generated artifact format and deployment metadata against the installed tooling before upload.

Do not treat authentication, permissions, invalid bindings, or application errors as networking failures. If the fallback fails, stop publication retries, preserve the diagnostic evidence, and report the incomplete release.

Hand forward the Worker deployment identifier, published revision, health and contract-check results, and any remaining configuration work. After Worker verification succeeds, complete any Pages production promotion deferred in step 2 using the loaded Pages skill.

## Completion check

Verify the canonical frontend reaches the intended backend and exercise the Scena flow affected by the change, including its asynchronous completion path when relevant. Confirm both deployed revisions and required configuration are consistent.

Report the Pages and Worker deployment identifiers, canonical URL, checks performed, and remaining blockers. Declare completion only when required production checks pass; clearly identify a working preview or partially published release as incomplete.
