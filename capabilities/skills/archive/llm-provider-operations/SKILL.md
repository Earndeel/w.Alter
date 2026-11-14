---
name: llm-provider-operations
description: "Use for LLM provider setup, evaluation, and routing."
version: 1.0.0
author: Hermes Curator
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [llm, providers, credentials, evaluation, routing, benchmarks]
---

# LLM Provider Operations

Use this class-level skill for onboarding LLM providers, proving account/model access, evaluating routes, comparing cost and quality, validating provider authenticity, and proposing router changes. Keep catalog facts, account entitlement, transport behavior, measured performance, and production integration as separate evidence layers.

## Provider setup and entitlement

- Resolve the exact provider, region, API mode, model ID, account, credential scope, billing path, and intended route before changing configuration.
- Store credentials in the vault or environment mechanism; never place keys, bearer tokens, cookies, OTPs, or client secrets in config, source, logs, prompts, or reports.
- Prefer least-privilege identities over root credentials and request only the scopes or permissions required for the task.
- Treat a catalog entry, model status, accepted agreement, use-case approval, inference profile, quota, billing entitlement, and successful inference as separate gates.
- Discover exact provider model IDs from the live provider catalog or official model card; never derive a hosted ID from a direct-API marketing name.
- Test the cheapest suitable model first, and clean up temporary cloud resources immediately so verification cannot become an unbounded bill.
- Restart or reload the actual gateway/process after provider configuration changes, then verify the route through a real request.

## AWS Bedrock branch

For Bedrock, check the gates in order: credential identity and IAM action, region/profile support, model catalog state, Anthropic agreement, console use-case form where required, account entitlement, effective quotas, and billing/Marketplace state. `ACTIVE` means the model exists; it does not prove that the account can invoke it.

Classify failures before changing anything:

- `ValidationException` usually indicates an invalid or unsupported model/profile identifier or API mode.
- `ResourceNotFoundException` can indicate a missing provider form or resource.
- `AccessDeniedException` can indicate IAM, agreement, entitlement, or zero effective quotas; inspect the relevant account checks instead of treating every denial as IAM.
- `ThrottlingException` can mean rate pressure, a daily limit, or a newly provisioned quota of zero; compare observed usage with service quotas before waiting or retrying.

Use the official console flow for provider forms and SaaS registration when no API exists. Do not treat a Marketplace button, bearer token, or successful authentication as proof of model access. Escalate only the affected quota/model family, preserve request IDs, and avoid opening broad duplicate requests.

## Evaluation and fair comparison

1. Define the claim, workload, provider route, model ID, account, budget, and evidence boundary.
2. Run a minimal authenticated smoke test through the intended client, then inspect request/session/provider metadata to prove which route handled it.
3. Normalize prompt, files, system instructions, tools, permissions, reasoning level, iteration cap, timeout, and output rubric across candidates.
4. Record wall time, tail latency, tool calls, tokens, cost, completion state, error class, and artifact quality; separate provider-aborted runs from model-quality results.
5. Test actual required behavior: JSON validity, tool calls, context handling, multimodal grounding, install/build/test execution, and visual or recipient-facing QA where relevant.
6. Re-fetch current prices, quotas, benchmark cohorts, and model catalogs before making time-sensitive recommendations.
7. Report measured, documented, derived, scenario, and unverified values separately. Never fill missing price or quality with zero.

Compare source-specific signals separately: general intelligence, coding, agentic/tool use, design/UI, vision/OCR, latency, context, and cost-per-successful-task. A leaderboard position, refusal style, or provider label alone is not a production recommendation.

## Router intelligence loop

Maintain a living evidence set rather than a static ranking. Collect official catalogs/pricing, benchmark scores, task-level tests, endpoint reliability, availability, expiry-bound offers, and qualitative community evidence with source URLs and confidence. Keep Artificial Analysis cost-per-task, human-preference/design views, token pricing, and provider credits as distinct dimensions.

Use a staged loop:

- **Signal collection:** ingest authoritative benchmarks, provider catalogs, pricing, availability, offers, and sourced community reports.
- **Test harness:** run a small stable task matrix only when the budget and route are approved; when paid tests are suspended, continue non-paid metadata and research ingestion.
- **Decision engine:** score per task and cost tier using quality, successful-task cost, speed, context, format/tool reliability, rate limits, availability, and evidence quality.
- **Integration proposal:** produce a reversible pseudo-diff with fallback, rollback, budget, and approval status; do not edit production routing automatically by default.

Define loop schemas and dry-run outputs before adding recurring jobs. Keep router decisions empty or explicitly provisional when pricing, coverage, or route evidence is incomplete.

## Benchmark and design-signal discipline

Always identify the source, category, view, metric family, cohort, and retrieval boundary. Do not mix Design Arena categories/views, synthetic benchmarks, human preference, and price-adjusted signals. If the requested slice is absent from the database, say so and ingest that slice before ranking.

Use community reports as qualitative hypotheses, risk modifiers, or test triggers—not as an unqualified score. Preserve source reputation, replication status, recency, hype, controversy, and confidence.

## Provider authenticity

For a new or suspicious endpoint, verify response headers, model listing, endpoint paths, response ID format, usage fields, tool-call schema, supported parameters, latency, billing metadata, and behavior under a small controlled probe. Compare with the official provider contract. A proxy may serve a good model yet remain an unsuitable route because it alters tools, identity, context, privacy, or reliability.

Do not infer identity from knowledge cutoff or refusal style alone. Stronger evidence includes provider-specific response IDs, native tool-use structures, exact model catalog membership, and consistent route metadata. Record competing hypotheses instead of asserting authenticity from one probe.

## Safe integration contract

- Prefer a small loopback adapter for CLI/subscription providers when native agent semantics are unnecessary; keep official authentication inside the official client.
- Isolate child-process credentials and remove conflicting provider environment variables only in that child.
- Verify health, model listing, request translation, actual Hermes invocation, restart behavior, picker visibility, and rollback before recommending a route.
- Keep experimental/self-hosted derivatives on separate endpoints until context, JSON, tools, repetition, latency, and task success are verified.
- State the exact provider, model, endpoint, region, route, evidence date, cost assumptions, unknowns, and approval status in every recommendation.
