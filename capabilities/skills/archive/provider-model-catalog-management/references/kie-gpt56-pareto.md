# Kie GPT-5.6 Pareto mapping example

A benchmark label combines a base model and, when parenthesized, a reasoning effort:

- `GPT-5.6 Sol (low|medium|high|xhigh|max)` → base ID `gpt-5-6-sol`
- `GPT-5.6 Luna (high)` → base ID `gpt-5-6-luna`

The effort suffixes are not separate published model IDs. In a Hermes installation where `/model` and `/reasoning` are separate, place only `gpt-5-6-sol` and `gpt-5-6-luna` in the Kie model catalog, then select the effort independently.

When reading a cross-provider Pareto chart, Xiaomi, DeepSeek, xAI, Anthropic, Meta, and other points remain under their respective provider catalogs. “All models on the chart” and “all Kie models on the chart” are different scopes and must not be silently conflated.

Verification checklist:

1. Both base IDs appear in the resolved Kie picker catalog.
2. The Kie transport remains Responses-compatible and preserves tools.
3. Each supported reasoning effort reaches the provider in its accepted payload shape.
4. Provider tests pass.
5. Configuration validation passes.
