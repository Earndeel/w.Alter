---
name: cloudflare-frontend-headless-delivery
description: "Use when a static site or frontend must be built or redesigned for Cloudflare Pages and needs local visual verification before delivery because browser_navigate is unavailable."
type: workflow
requires: [cloudflare-pages-deploy, design-frontend-specialization, headless-screenshot-qa]
---

# Cloudflare frontend delivery with headless QA

## Scope and execution order

Orchestrate the existing skills; delegate their implementation details rather than reproducing them here.

Use this chain when the task combines Cloudflare Pages deployment or troubleshooting, frontend design work, and fallback local visual QA. If the hosted browser works, use its normal QA path instead. For framework applications, use the framework server and integration tests rather than treating the source tree as standalone HTML.

The initial order is **deployment discovery → frontend implementation → headless QA**. The first deployment step is preparation, not permission to publish an unreviewed redesign. After QA and any required approval, return to the deployment skill to release the verified artifact.

Maintain a handoff record containing the target, source revision, build directory, route/interaction acceptance criteria, evidence paths, unresolved blockers, and approval status. Never include secret values.

## 1. Establish the deployment contract

**load cloudflare-pages-deploy with skill_read**

Use the sub-skill to discover the existing hosting architecture, identify the exact Pages project and domain ownership, establish authentication readiness, and determine the build/output contract. Do not create duplicate projects or modify production merely to complete discovery. If discovery reveals a different hosting platform, stop and select the appropriate deployment workflow.

**Hand off to design:** repository and working directory; confirmed deployment target; build command and output directory; public routes; existing backend integrations; domain requirements; constraints and production-review requirements.

**Gate:** the intended target and integration boundaries are unambiguous. Resolve missing access or target ambiguity before any deployment action. Design may continue locally with explicitly documented deployment blockers.

## 2. Build or redesign against that contract

**load design-frontend-specialization with skill_read**

Load this skill before any design or implementation work, and follow its companion-skill and reference requirements. Use the deployment contract to preserve existing routes and behavioral integrations while implementing the requested design.

Define acceptance criteria for the actual task, covering representative desktop/mobile layouts, essential interactions, accessibility, motion behavior, and any existing application contracts. Produce a reproducible local build or preview without publishing to production.

**Hand off to QA:** exact source revision and build artifact; server/start instructions; route and interaction matrix; expected visual direction; relevant viewports; animation/reveal behavior; known limitations.

**Gate:** the build succeeds, required routes and assets exist, and the preview serves the intended artifact. A build success is not visual approval or proof that interactions work.

## 3. Verify the local artifact

**load headless-screenshot-qa with skill_read**

Confirm that the hosted browser is unavailable, then apply the sub-skill's supported local capture and verification approach. For framework apps, retain their server and integration-test path and use applicable headless regression references rather than substituting a simple file server.

Evaluate the acceptance matrix from step 2. Collect desktop/mobile visual evidence and behavioral results. Distinguish capture artifacts from actual rendering defects, and do not accept screenshots alone as proof of route or interaction correctness.

**Hand off to release:** tested artifact identity; screenshots and relevant measurements; route/interaction results; console/network findings; defects and severity; explicit pass/fail status.

**Gate:** blocking defects return to step 2, followed by a fresh build and rerun of affected checks. If QA tooling is unavailable, report verification as blocked rather than passed. Present evidence and obtain any review required by the design skill before production release. Approval applies only to the reviewed artifact; material changes require renewed QA and review.

## 4. Release and verify the same artifact

**load cloudflare-pages-deploy with skill_read**

Resume deployment only after the QA gate and applicable approval gate pass. Reconfirm the target and deploy the verified output, not an untested rebuild. If rebuilding changes the artifact, return to QA.

Follow the deployment skill's production-verification guidance to establish that the immutable deployment and intended canonical URL serve the expected content and assets. Check relevant direct-entry routes and domain status. If public browser regression is required, **load headless-screenshot-qa with skill_read** and apply its relevant deployed-site checks.

**Completion gate:** distinguish upload success, live-content verification, domain readiness, and visual/functional verification. Do not claim completion while a required gate is unresolved.

## Delivery

Report the deployed URLs in plain text, the artifact/revision delivered, checks completed, evidence locations, and any remaining limitations. If release is blocked, provide the verified local or preview status and the precise next action instead of claiming the site is live.
