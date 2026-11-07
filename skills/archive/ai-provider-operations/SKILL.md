---
name: ai-provider-operations
description: "Use for LLM and media provider setup, routing, and QA."
version: 1.0.0
author: Hermes Curator
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [llm, media, providers, routing, evaluation, generation, qa]
---

# AI Provider Operations

Use this class-level umbrella for LLM and media provider onboarding, entitlement checks, routing, evaluation, generation, post-production, and delivery QA. Keep provider facts, account access, local tracking, measured quality, and recipient-visible results separate.

## Always-on rules

- Resolve exact provider, region, account, model ID, endpoint, API mode, modality, inputs, output contract, budget, and approval before changing a route or starting billable work.
- Discover case-sensitive model IDs and live contracts from authoritative provider catalogs or documentation; marketing names, generic model lists, and successful authentication do not prove invocability.
- Verify the effective invocation surface, not only provider selection: the toolset must be enabled, the current session schema must expose the capability, and the adapter must send the requested model and controls; provider configuration or valid OAuth alone proves none of these.
- Keep credentials in approved secret stores and child-process scope; never place tokens, cookies, signed URLs, private paths, or task manifests in prompts, logs, or reports.
- Separate catalog availability, account entitlement, permissions, quota, transport, provider execution, local tracking, artifact validity, and recipient access; diagnose failures at the layer that produced their evidence.
- Use narrow adapters with correlation IDs, explicit payloads, durable job state, retry lineage, and idempotent transitions. Poll the original job after interruption rather than creating a duplicate.
- Compare providers with normalized prompts, inputs, tools, permissions, timeouts, budgets, and rubrics. Record latency, tokens, cost, errors, successful-task rate, and artifact quality separately; never invent missing values.
- For media, bind actual source bytes or provider handles and preserve hashes, dimensions, prompts, and stage receipts. A task ID, success label, URL, or lazy gallery tile is intermediate evidence until the downloaded artifact passes metadata, full decode, visual, audio, and brief QA.
- Keep generation, edit, caption, audio, browser playback, and final delivery as separate gates. Preserve clean masters, render revisions from them, and verify the exact recipient-visible attachment or playback target.
- Require explicit approval for paid generation, production routing, public delivery, and irreversible changes; run cheap non-billable contract checks before committing spend.

## LLM provider branch

Check identity, IAM, region, catalog state, agreement, entitlement, quota, billing, and API mode in that order. Classify validation, not-found, access, and throttling failures before changing identifiers or retrying. Propose reversible routing changes with fallback, rollback, budget, and approval status rather than editing production dispatch automatically.

## Media generation branch

Define reference binding, continuity, shot timing, output format, post-production timeline, ASR/caption policy, loudness, codec fallback, and delivery path before submission. Treat generated text, logos, legal claims, URLs, and speech as untrusted output; replace or reject them when exact copy matters.

## Evaluation and release branch

Run a representative task matrix, inspect actual request and response metadata, decode and review artifacts, and report provider failure, technical failure, visual/audio failure, brief non-compliance, partial completion, and recipient-access limits separately.

## Completion contract

A route or commission is complete only when the intended provider execution, artifact, downstream processing, and delivery result have each been read back and verified. Report exact IDs, measured facts, cost assumptions, unverified constraints, and cleanup state.

Read `references/provider-and-media-gates.md` for the branch checklists. Google Flow UI quirks (policy wording, agent cost gates, ingredient chips, signed exports, duration caps) are in `references/flow-google-ui.md`.
