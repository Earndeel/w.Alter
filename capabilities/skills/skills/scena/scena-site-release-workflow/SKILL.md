---
name: scena-site-release-workflow
description: Use when a Scena feature or repair spans the video agent or SaaS backend, Cloudflare Pages delivery, and a polished frontend implementation or redesign.
type: workflow
requires: [scena-video-factory, cloudflare-pages-deploy, design-frontend-specialization]
---

# Scena Site Release Workflow

Orchestrate the existing skills; keep implementation recipes and operational rules in their source skills. Load only references relevant to the task. This workflow does not authorize additional production changes.

## When the chain applies

Use for a Scena change that needs all three: agent or SaaS integration work, Pages deployment coordination, and frontend design. For isolated backend, deployment, or design requests, use the relevant skill directly.

Follow Scena → Pages preparation → frontend implementation. Then return to Pages for release of the reviewed frontend. Pages preparation establishes the delivery contract; it does not publish an unfinished redesign.

## 1. Establish the Scena integration contract

load scena-video-factory with skill_read.

Use it to inspect the current project, diagnose the affected behavior, and implement the required engine or SaaS changes. Resolve relevant contradictions in historical references against live configuration and source before choosing an implementation.

Hand to step 2:
- Source revision and affected services or frontend surfaces.
- Frontend-facing API contract, authentication behavior, tenant context, async job states, and error behavior.
- Required public configuration, backend deployment dependencies, and regression results.

Gate: the affected backend behavior must be verified and the frontend contract explicit. If an unresolved backend issue changes the contract, finish that investigation before preparing delivery around assumptions.

## 2. Establish the Pages delivery contract

load cloudflare-pages-deploy with skill_read.

Use its discovery procedure to identify the existing account, project, domain ownership, frontend source, build output, and relationship to the Scena backend. Determine the preview and production targets and any release dependencies. Deploy only already-ready artifacts within the authorized scope; defer the redesigned frontend until step 3 passes.

Hand to step 3:
- Confirmed Pages project and target URLs, with preview versus production identified.
- Build command, output directory, routing requirements, and public environment configuration.
- Backend endpoints and integration constraints from step 1.
- Baseline deployment evidence and any delivery blockers.

Gate: source, build output, domain, and backend must belong to the intended application and environment. Resolve ambiguous ownership or missing configuration before implementation depends on them.

## 3. Build and review the frontend

load design-frontend-specialization with skill_read.

Load it before starting frontend implementation, together with any companions it requires. Apply its design and verification process using the integration and delivery contracts from the previous steps.

Hand back to step 2:
- Tested frontend revision and reproducible build artifact.
- Browser smoke results for the affected user journeys against the intended backend.
- Screenshots or preview URL and the visual review outcome.
- Remaining issues and production authorization status.

Gate: design checks, integration checks, and the sub-skill's visual review checkpoint must pass before production release. A preview is not evidence that production has been updated.

## Release and recovery

load cloudflare-pages-deploy with skill_read again for the release pass.

Deploy the reviewed artifact to the confirmed target using its deployment and production-verification procedures. Verify the canonical URL, deployed content and assets, and affected Scena journeys before reporting completion.

Route backend or contract failures back to step 1, delivery failures to step 2, and visual or interaction failures to step 3. Recheck downstream handoffs whenever their inputs change. Stop production promotion while a required gate remains unresolved; report the specific blocker and available preview evidence.

Finish with the released revision, verified URLs, validation outcome, and any outstanding limitations.
