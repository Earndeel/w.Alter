---
name: provider-model-catalog-management
description: Map provider model catalogs and benchmark/Pareto chart labels into Hermes model pickers without conflating model IDs with reasoning settings.
version: 1.0.0
---

# Provider Model Catalog Management

Use this skill when adding, removing, consolidating, or validating models shown in a Hermes `/model` picker, especially when the requested list comes from a benchmark chart.

## Core workflow

1. Return to the original source (image, provider catalog, or API documentation) and transcribe labels exactly. Do not reconstruct a requested list from a prior prose summary.
2. Split each chart label into:
   - provider,
   - base model identity,
   - inference setting such as reasoning effort.
3. Verify every base model ID against the provider's authoritative source or live catalog. Load `model-id-lookup` before committing IDs.
4. Keep cross-provider benchmark points under their actual providers; do not copy the entire chart into whichever provider happens to be under repair.
5. Update the provider's static fallback catalog and the user's curated picker configuration when both exist.
6. Verify the actual picker resolution path and run provider tests plus configuration validation.

## Reasoning variants are not automatically models

A label such as `Model X (low)` generally means one model ID plus an inference parameter. Do not invent IDs such as `model-x-low` unless the provider publishes that exact ID or Hermes implements an explicit virtual-preset layer. If model and effort are selected separately, expose the base ID in `/model` and use the reasoning control for the effort.

## Required verification

Validate these independently:

- exact API model ID;
- provider routing and transport;
- visibility in the real `/model` catalog;
- reasoning effort propagation;
- provider-specific effort mapping;
- tests and configuration health.

A green transport test does not prove picker visibility. That distinction matters whenever one sibling model works while the requested sibling is absent — a surprisingly popular configuration aesthetic.

## Hermes-specific notes

- Use the supported Hermes configuration command for guarded configuration files rather than forcing a direct edit.
- The catalog resolver is `hermes_cli.models.provider_model_ids(provider)` in current Hermes versions; confirm against current source before relying on that name.
- A live provider catalog may merge additional models beyond the curated Pareto subset. Report the actual resolved list, not merely the list written into configuration.

See `references/kie-gpt56-pareto.md` for a concrete mapping example.
See `references/scena-kie-routing-split.md` for a complete provider routing split recommendation (Claude/Gemini/GPT) from a production Cloudflare Worker codebase audit.
