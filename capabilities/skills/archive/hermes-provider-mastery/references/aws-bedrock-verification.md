# AWS Bedrock Model Access & Verification

This guide covers debugging Bedrock model invocation failures, recognizing credential issues vs. entitlement limits, and parsing Bedrock exception patterns.

## Ground Truth: List vs. Access Entitlements

In AWS Bedrock, calling list APIs does **not** reflect active model access:
- `aws bedrock list-foundation-models` and `aws bedrock list-inference-profiles` output all models/profiles defined in the region that are globally `ACTIVE`.
- You can see a model listed as `status: ACTIVE` in these summaries even if your account has **not** requested or been granted access to it.

## Common Bedrock Exception Signatures

When testing connectivity via `aws bedrock-runtime invoke-model` or through the Hermes adapter:

### 1. `AccessDeniedException`
* **Signature**:
  ```
  An error occurred (AccessDeniedException) when calling the InvokeModel operation: <model_id> is not available for this account. You can explore other available models on Amazon Bedrock.
  ```
* **Meaning**: The model ID is correct, the AWS credentials and region are correct, but the AWS account has not completed the "Model Access" request in the AWS Console for that model.
* **Resolution**: Go to AWS Bedrock Console → Model Access → Request Model Access, check the box for the specific model, and submit.

### 2. `ValidationException`
* **Signature**:
  ```
  An error occurred (ValidationException) when calling the InvokeModel operation: The provided model identifier is invalid.
  ```
* **Meaning**: The model ID string is completely unrecognized or typoed. It does not exist in the targeted region or environment.
* **Example**: Passing `us.anthropic.claude-opus-4-8-20260213-v1:0` might fail with `ValidationException` if Bedrock only registers the short system inference profile `us.anthropic.claude-opus-4-8` or standard model `anthropic.claude-opus-4-8` in your region.

### 3. `ThrottlingException`
* **Signature**:
  ```
  An error occurred (ThrottlingException) when calling the InvokeModel operation: Too Many Requests.
  ```
* **Meaning**: The account has access, but the active concurrency or TPS quota has been exhausted. Usually resolves with exponential backoff or when service quotas are lifted.

---

## Verified Inference Profile IDs («secret:vault»)

| Model Name | Inference Profile ID (In-Region Routing) |
|---|---|
| Claude Fable 5 | `us.anthropic.claude-fable-5` |
| Claude Opus 4.8 | `us.anthropic.claude-opus-4-8` |
| Claude Sonnet 4.6 | `us.anthropic.claude-sonnet-4-6` |
