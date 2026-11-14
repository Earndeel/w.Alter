# Anthropic Claude 5 availability on Amazon Bedrock

## Verified catalog state (2026-08-02)

AWS Bedrock's official model cards list **Claude Opus 5** and **Claude Sonnet 5** as active Anthropic models, with a 1M-token context window and 128K maximum output. The model cards show a June 30, 2026 launch date and no EOL date.

Use the exact profile IDs below; do not silently substitute a nearby Claude generation:

| Model | Global profile | US geo profile | EU geo profile |
|---|---|---|---|
| Opus 5 | `global.anthropic.claude-opus-5` | `us.anthropic.claude-opus-5` | `eu.anthropic.claude-opus-5` |
| Sonnet 5 | `global.anthropic.claude-sonnet-5` | `us.anthropic.claude-sonnet-5` | `eu.anthropic.claude-sonnet-5` |

The model cards also expose the plain in-region IDs (`anthropic.claude-opus-5` and `anthropic.claude-sonnet-5`) where the target region supports them. The regional-availability table includes `ap-southeast-7` (Thailand) for these model profiles in the verified catalog state.

## Catalog availability is not account entitlement

A model appearing in AWS documentation does **not** prove that a particular AWS account can invoke it. Check all of the following separately:

1. the target region and inference-profile type are supported;
2. the account's Bedrock model access/Anthropic entitlement is enabled where AWS requires it;
3. IAM permits the API path in use (`bedrock:Converse` and/or `bedrock:InvokeModel`);
4. quotas and billing are available.

If Monsieur asks whether *his* account is enabled, inspect the configured AWS profile and region or run a real Bedrock discovery/invocation check; answer "catalogue disponible" and "compte habilité" separately.

## Primary sources

- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html

## Operational caution

Model IDs, regions, and lifecycle status can change. Re-check the official AWS model card and regional availability page immediately before writing Hermes configuration or a production router; never infer an ID from a model's marketing name.
