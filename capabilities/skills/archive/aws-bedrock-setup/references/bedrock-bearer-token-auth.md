# Bedrock Bearer Token Authentication

AWS Bedrock supports bearer token auth (in addition to IAM/SigV4). Useful when you have a Claude Platform on AWS subscription that provisions API keys.

## Token Format

Starts with `ABS` prefix. Passed via `Authorization: Bearer` header instead of IAM SigV4 signing.

## API Usage

Same Bedrock Runtime endpoint, different auth header:

```python
import requests, json

headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer <TOKEN>"  # ABS prefix token
}

# Invoke model (must use inference profile prefix us.anthropic.*)
r = requests.post(
    "https://bedrock-runtime.us-east-1.amazonaws.com/model/us.anthropic.claude-haiku-4-5-20251001-v1:0/invoke",
    headers=headers,
    json={
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 50,
        "messages": [{"role": "user", "content": "Say OK"}]
    },
    timeout=15
)
print(r.status_code, r.json())
```

## Model Access with Bearer Token (Verified 2026-06-13)

Bearer token auth does NOT bypass model access restrictions. The token authenticates you, but model availability depends on the AWS account's model access settings:

| Model | Bearer Token | IAM (boto3) | Notes |
|-------|-------------|-------------|-------|
| Haiku 4.5 | ✅ | ✅ | Works with inference profile `us.anthropic.*` |
| Sonnet 4.6 | ✅ | ✅ | Works with inference profile `us.anthropic.*` |
| Opus 4.8 | ❌ 403 | ❌ 403 | Account-level block, not auth |
| Fable 5 | ❌ 403 | ❌ 403 | Account-level block, not auth |

**Key insight**: If a model returns 403 with IAM credentials, it will also return 403 with a bearer token. The token is an alternative auth method, not an alternative access method.

## Inference Profile Requirement

Newer models (Haiku 4.5, Sonnet 4.6, Opus 4.8, Fable 5) require inference profile IDs (`us.anthropic.*` prefix) for on-demand invocation. Raw model IDs return 400:

```
"Invocation of model ID anthropic.claude-haiku-4-5-20251001-v1:0 with on-demand throughput isn't supported."
```

Always use `us.anthropic.*` prefix for these models.

## Pitfalls

1. **Bearer token ≠ model access** — Token handles authentication only. Model access is controlled at the account level (EULA + use case form + quotas).
2. **Same 403 errors** — Bearer token gives identical results to IAM credentials for model access. Don't expect it to unlock blocked models.
3. **Hermes integration** — Hermes Bedrock provider uses IAM auth (SigV4 via boto3). Bearer token auth requires a custom provider or direct API calls. Not natively supported by the `bedrock` provider in Hermes.
4. **Token is a secret** — Store in environment or secure vault, never in config files or version control.
