---
name: hermes-nous-tool-gateway
description: "Use when routing Nous-hosted tools through Hermes."
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [hermes, nous, portal, tool-gateway, oauth, video-generation, flux]
    related_skills: [hermes-agent, hermes-provider-mastery, web-service-browser]
---

# Hermes Nous Tool Gateway

Use this skill when a Nous Research announcement exposes a capability inside Hermes Agent — especially video/image generation, hosted tools, or a preview model — and the user expects the request to run through Nous rather than a direct vendor API.

## Core distinction

Do not conflate these three layers:

1. **LLM inference provider** — `model.provider: nous` sends chat/model calls through Nous Portal.
2. **Managed tool gateway** — Hermes sends a tool request such as `video_generate` through a Nous-hosted vendor gateway, using the user's Nous OAuth token and entitlement.
3. **Direct vendor API** — a local key such as `FAL_KEY` calls the vendor directly and bypasses the Nous-managed route.

A Nous-hosted preview can use the managed gateway even when the local machine has no vendor key. A direct FAL key is a fallback path, not a prerequisite. Never add, request, or silently substitute a direct vendor credential when the user's intent is “via Nous Research”.

## Standard workflow

1. **Identify the promised surface.** Determine whether the announcement says “inside Hermes Agent”, “via Nous Portal”, or names a direct vendor API. “Inside Hermes Agent” means inspect Hermes tools/provider routing first; it does not mean opening the public subscription page as the generation UI.
2. **Check the installed Hermes version and local capability.** Use `hermes --version`, `hermes tools list`, and the live/local provider catalog. Do not infer that a feature exists merely because it appears in a social post.
3. **Restore Nous OAuth through the CLI device flow.** Use `hermes auth add nous --type oauth`. Keep the process polling and open the printed `verification_uri_complete` URL. The browser is only for device approval; the CLI persists the OAuth state.
4. **Handle user authentication honestly.** If Google/Privy requires a passkey, OTP, or MFA, pause and ask the user to approve it. Do not bypass or guess an account. A stale refresh token must be replaced by a fresh device flow.
5. **Enable the relevant Hermes toolset.** For video, use `hermes tools enable video_gen`; remember tool/config changes apply to a new session or reset.
6. **Confirm managed routing before generation.** Check `hermes status` and `hermes portal info`. For the video tool, the managed FAL queue is resolved through Nous when the account is logged in and entitled; the exact gateway readiness must be checked at runtime.
7. **Verify the exact model.** A local fallback catalog may contain PixVerse, Veo, Seedance, or other models while a Nous preview is server-side. If the user requests FLUX 3, do not substitute another model or confuse FLUX 2 image models with FLUX 3 video. If the exact route is not exposed, report that fact.
8. **Run the smallest real test only after entitlement is clear.** Use a short prompt, conservative duration/resolution, and no optional audio unless the preview contract says otherwise. Treat the result as unverified until the returned artifact URL/path is fetched or stat'ed and its media type/duration are checked.

## Hermes implementation pattern

The repository's video surface is provider-agnostic:

- `video_generate` is the stable tool surface.
- The FAL video plugin can resolve a managed `fal-queue` gateway through `tools.managed_tool_gateway.resolve_managed_tool_gateway()`.
- Managed readiness depends on Nous login and tool entitlement (`managed_nous_tools_enabled()`), not merely on a local FAL key.
- The gateway token is read/refreshed from the Hermes Nous auth store; `TOOL_GATEWAY_USER_TOKEN` is an explicit override, not something to invent.

Therefore, when the user says “via Nous”, prefer the managed route and preserve the requested model ID. Direct vendor mode is allowed only when the user explicitly asks for it or approves it as a fallback.

## Verification checklist

```bash
hermes --version
hermes status
hermes tools list
hermes portal info
```

For a fresh login:

```bash
hermes auth add nous --type oauth
# approve the printed device URL in a browser
hermes status                 # Nous Portal: logged in
hermes tools enable video_gen
# start a new Hermes session/reset before invoking video_generate
```

See `references/nous-managed-tool-gateway.md` for the source-level routing map, device-flow behavior, and failure interpretation.

## Pitfalls

- **Public Portal page ≠ generation UI.** `/manage-subscription` is an account/entitlement surface; do not use it as proof that FLUX is available or as the primary generation workflow.
- **No silent FAL fallback.** If managed Nous routing is unavailable, do not quietly send the job to direct FAL, PixVerse, Veo, or another model.
- **No stale-token loop.** `Invalid refresh token` means re-authenticate with the device flow; retrying refresh does not repair it.
- **No model-name inference.** A social announcement's “FLUX 3 Preview” label is not enough to invent a local model ID. Confirm the live capability and retain the exact requested ID.
- **No fabricated success.** A successful request submission is not a generated video; verify the final artifact and return the real URL/path, status, and provider route.
- **No broad process termination.** Stop only the current OAuth/test process if needed; never use broad `pkill` while recovering a waiting device flow.
