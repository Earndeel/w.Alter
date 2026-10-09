# Nous-managed tool gateway: routing and preflight

## Why the browser route was misleading

The public Nous Portal route (`/manage-subscription`) is an account, plan, and entitlement surface. It is **not** the FLUX/Hermes generation UI. A device-code URL may reuse that route with a `user_code` query parameter, but opening it is only correct for approving OAuth; generation still happens from Hermes afterward.

For a Nous announcement that says a capability is available “inside Hermes Agent”, start with Hermes' provider/tool path. Do not open the plan page first and infer capability from the visible plans.

## Verified source-level routing map

Observed in the Hermes repository during the FLUX 3 test:

- `tools/video_generation_tool.py` exposes the backend-neutral `video_generate` tool.
- `agent/video_gen_registry.py` selects the configured video provider; with no explicit provider it only auto-selects when exactly one registered provider is available.
- `plugins/video_gen/fal/__init__.py` supports a managed `fal-queue` route through `tools.managed_tool_gateway.resolve_managed_tool_gateway()`.
- `tools/managed_tool_gateway.py` builds the default vendor gateway as `https://fal-queue-gateway.nousresearch.com`, reads the Nous OAuth access token from the Hermes auth store, and refuses readiness without a token.
- `tools/tool_backend_helpers.py::managed_nous_tools_enabled()` requires a logged-in Nous account and `tool_gateway_entitled`; an arbitrary local FAL key is not proof of Nous entitlement.

The FAL plugin's intended decision is effectively:

```text
if direct FAL credentials exist and gateway is not preferred:
    use direct FAL
else:
    resolve the Nous-managed fal-queue gateway
```

Thus “via Nous Research” means: authenticate Nous, confirm entitlement, select the Hermes video tool/provider, and let the provider resolve the managed gateway. Do not add `FAL_KEY` merely to make the tool appear available.

## Correct OAuth recovery

Use the CLI device flow, not a browser subscription workflow:

```bash
hermes auth add nous --type oauth
```

Hermes requests a device code from `/api/oauth/device/code`, prints a `verification_uri_complete` URL and a short user code, then polls `/api/oauth/token`. The printed verification URL can visually resemble the public Portal plan page; that is normal for the authorization step. It is not the generation endpoint.

If `hermes status` reports `Invalid refresh token`, start a fresh device flow. Do not repeatedly refresh the stale token and do not silently fall back to direct FAL. The user may need to approve Google/Privy with a passkey, OTP, or MFA; stop and request that approval instead of bypassing it.

After approval:

```bash
hermes status
hermes portal info
hermes tools enable video_gen
```

Tool/config changes require a new Hermes session or reset before the tool schema is rebuilt.

## FLUX 3-specific guardrails

The local Hermes source may expose fallback FAL families (for example PixVerse, Veo, Seedance, or LTX) while a Nous preview model is delivered server-side. The absence of `flux-3` in a local static catalog is not enough to prove that the managed preview is unavailable; inspect the live Nous/Hermes capability. Conversely, the social-post label is not permission to invent a model ID.

For a requested FLUX 3 test:

1. Preserve the exact requested model/capability name.
2. Confirm the managed provider and entitlement before submission.
3. Use a short, conservative test prompt and parameters.
4. Do not substitute another video model without telling the user and getting approval.
5. Verify the final artifact URL/path, HTTP status, media type, and duration before reporting success.

A successful tool submission or queue ID is not proof that a video was generated. The final output must be fetched or stat'ed and, when relevant, visually inspected.

## Session evidence that prompted this reference

- Hermes reported Nous OAuth as not logged in with an invalid refresh token.
- `video_gen` was disabled and no `video_gen` section was present in `config.yaml`.
- A direct FAL key was present, but the user's explicit requirement was to route through Nous; using that key would have tested the wrong billing/auth path.
- The correct next step was a fresh `hermes auth add nous --type oauth` device flow, followed by enabling `video_gen` and verifying managed routing.
