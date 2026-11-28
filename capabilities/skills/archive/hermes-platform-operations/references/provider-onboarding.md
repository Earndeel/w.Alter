# Provider Onboarding and Live Verification

Use this reference when adding an external LLM provider to Hermes, especially an OpenAI-compatible service whose credential is issued from a web dashboard.

## Ordered procedure

### 1. Freeze the target and scope

Identify the active Hermes home/profile, authoritative config file, gateway/process owner, intended provider ID, exact endpoint, exact model ID, and credential environment-variable name. Keep the main model route separate from delegation, cron, auxiliary, and fallback routes; each can resolve independently.

### 2. Prove catalog availability

Query the provider's live model catalog before changing Hermes configuration. Require an exact, case-sensitive ID match; a similar name, alias, or fallback response does not prove availability. For an OpenAI-compatible catalog, the usual probe is:

```python
import json
import urllib.request

base_url = "https://provider.example/v1"
requested_model = "<exact-model-id>"

with urllib.request.urlopen(f"{base_url}/models", timeout=20) as response:
    payload = json.load(response)
ids = {item.get("id") for item in payload.get("data", [])}
assert requested_model in ids, "The exact requested model is not in the live catalog"
print("catalog_ok", requested_model)
```

Do not silently rewrite the requested ID or substitute a nearby model when this check fails.

### 3. Complete authentication and issue the credential

Finish sign-in, MFA, identity, billing, and account-entitlement steps in the provider's browser session. The agent must not request, copy, or process a one-time MFA code from chat. Apply the active human-in-the-loop approval gate before a sensitive key-issuance action.

Create one named key for the target Hermes profile. Count it as issued only after reading back the provider's key list, status card, or documented response that proves the key exists. If the dashboard stalls, navigates ambiguously, or returns an unclear result, reload and read state before retrying; blindly clicking again can create duplicate credentials even when the first request completed.

Store the secret directly in the approved vault or Hermes `.env` path. Never print it, place it in `config.yaml`, pass it as a command argument, include it in screenshots/request dumps, or paste it into chat. Configuration must carry only the environment-variable name.

### 4. Configure and reload Hermes

Set the provider name, API/base URL, exact default model, exact model list, and `key_env` explicitly. Verify the YAML types after writing—particularly that model collections are lists—and verify the environment check with a boolean presence result only:

```bash
test -n "${PROVIDER_KEY_ENV:-}" && printf '%s\n' credential_present || printf '%s\n' credential_absent
```

Replace `PROVIDER_KEY_ENV` with the literal variable name through the shell's normal environment lookup; do not put the secret in the command. Restart or reload the actual Hermes gateway/process owner because an already-running session may retain the old provider map. Read back the active process/config identity after the reload.

### 5. Exercise the real Hermes path

Run a deterministic, minimal canary with both provider and model explicit:

```bash
hermes chat -q "Reply with exactly OK" \
  -m <exact-model-id> \
  --provider <provider-id> -Q
```

A transport status alone is insufficient. Parse the response or SSE envelope for embedded error objects, then inspect a redacted request log/dump or provider-side trace and verify the outbound URL, provider, and exact model. Never treat a local catalog response, HTTP 200 with an error body, or a fallback model response as proof of successful inference on the intended route.

### 6. Classify evidence and stop cleanly

Keep these claims separate in the report:

- catalog availability;
- account/session authentication;
- credential issuance and local binding;
- Hermes config reload;
- real inference entitlement and response.

If a gate is unverified, say so and stop at that gate rather than presenting the integration as complete. Do not repeat a sensitive mutation merely because the UI failed to render its result; obtain read-back evidence or use an explicitly approved alternative. For error triage, distinguish missing/invalid credentials (`401`), provider policy or entitlement (`403`), wrong endpoint/model (`404`), and application-level errors returned inside a successful HTTP response.
