# Claude Fable 5 zero-quota / AccessDenied escalation

Observed pattern for Bedrock `anthropic.claude-fable-5` on account-level gating:

- `get-foundation-model` returns model `ACTIVE`.
- `get-foundation-model-availability` returns:
  - `agreementAvailability.status=AVAILABLE`
  - `authorizationStatus=AUTHORIZED`
  - `entitlementAvailability=AVAILABLE`
  - `regionAvailability=AVAILABLE`
- `get-inference-profile us.anthropic.claude-fable-5` returns `ACTIVE`.
- `invoke-model --model-id us.anthropic.claude-fable-5` still fails:
  - `AccessDeniedException: anthropic.claude-fable-5 is not available for this account`
- Service Quotas show Fable 5 quotas at zero.

Relevant Fable 5 quota codes in `«secret:vault»`:

| Quota code | Name | Adjustable | Notes |
|---|---|---:|---|
| `L-D06938E7` | Global cross-region model inference tokens per minute for Anthropic Claude Fable 5 | Yes | Request SQI |
| `L-9B258944` | Cross-region model inference tokens per minute for Anthropic Claude Fable 5 | Yes | Request SQI |
| `L-2775684C` | Global cross-region model inference tokens per day for Anthropic Claude Fable 5 | No | AWS must seed/raise internally |
| `L-23057DDF` | Model invocation max tokens per day for Anthropic Claude Fable 5 (doubled for cross-region calls) | No | AWS must seed/raise internally |

## Action pattern

1. Do not chase IAM once availability is `AUTHORIZED/AVAILABLE` and the inference profile is `ACTIVE`.
2. Request only the two adjustable Fable 5 token/min quotas first, with `DesiredValue=20000001.0` to pass the phantom-default validation pattern seen on Bedrock quotas.
3. Re-check `list-requested-service-quota-change-history` after a few minutes. `PENDING` commonly turns into `CASE_OPENED` with a `CaseId`.
4. If `CASE_OPENED`, add an escalation note to each case because the non-adjustable token/day quotas remain zero until AWS internally reviews/seeds the account.
5. Avoid opening broad SQI batches for unrelated models; too many open SQIs can block further requests.

## Escalation template

```text
Amazon Bedrock Anthropic Claude Fable 5 is visible and availability checks show AUTHORIZED / AVAILABLE / region AVAILABLE. The inference profile us.anthropic.claude-fable-5 is ACTIVE. However all effective Fable 5 quotas are 0, including tokens per minute and non-adjustable tokens per day, causing InvokeModel to fail with AccessDeniedException: anthropic.claude-fable-5 is not available for this account.

Account: <ACCOUNT_ID>
Region: «secret:vault»
Model: anthropic.claude-fable-5
Inference profile: us.anthropic.claude-fable-5
Adjustable zero quotas: L-D06938E7, L-9B258944
Non-adjustable zero quotas: L-2775684C, L-23057DDF

Please review Bedrock/Anthropic account eligibility and seed baseline quotas for Claude Fable 5. Use case form has been submitted and model availability API returns authorized/available.
```
