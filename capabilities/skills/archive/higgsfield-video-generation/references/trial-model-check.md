# Higgsfield Trial Model Availability

Snapshot from 2025-07-05 on a trial workspace (plan_type "plus" but trial-enforced).

## Video Models

| Model ID | Trial Status | Notes |
|---|---|---|
| `cinematic_studio_3_0` | ✅ Works | ~80 credits per 8s video, 720p |
| `kling3_0_turbo` | ❌ Trial blocked | `only_mcp_usage_on_trial_is_available` |
| `kling-v1-6` | ❌ Trial blocked | `only_mcp_usage_on_trial_is_available` |
| `veo3_1` | ❌ Trial blocked | `only_mcp_usage_on_trial_is_available` |
| `wan2_2-t2v_turbo` | ❌ Trial blocked | `only_mcp_usage_on_trial_is_available` |
| `gemini_omni` | ❌ Backend error | Different error from trial — model broken on server |
| `gemini_flash` | ❌ Unknown model | Server returns "unknown model" |
| `cinematic_studio_3_5` | ❌ Unknown model | Does not exist on server |

## Credit Tracking

```bash
higgsfield workspace list --json
# → credits: current balance
```

cinematic_studio_3_0 cost: ~80 credits for 8s at 720p. Starting balance 121 → 41 after one generation.

## Resolution Note

cinematic_studio_3_0 outputs 720p vertical (3:4). Aspect ratio 16:9 may not be supported on this model.