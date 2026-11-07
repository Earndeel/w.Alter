---
name: grok-cli-integration
description: "Use and integrate the official xAI Grok Build CLI safely: subscription OAuth, headless coding runs, Hermes worker routing, and the distinction from the billable xAI API."
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [Grok, xAI, CLI, Coding-Agent, OAuth, Hermes, Provider-Integration]
    related_skills: [hermes-agent, codex, claude-code, hermes-provider-mastery]
---

# Grok Build CLI Integration

Use this skill when the user wants Grok Build, the `grok` CLI, `grok-build-0.1`, Grok subscription access from Hermes, or a Grok-powered coding worker.

## Core distinction: three access paths

Never conflate these paths:

1. **Grok web UI** — browser session and web entitlement.
2. **Direct xAI API** — `https://api.x.ai/v1`, `XAI_API_KEY` or Hermes xAI OAuth, pay-as-you-go billing and spending limits.
3. **Grok Build CLI** — official `grok` binary, `grok login`, subscription-backed credential store, and a separate CLI inference service.

A `402 personal-team-blocked` from `api.x.ai` proves only that the direct API billing path is blocked. It does not prove that the official CLI subscription path is unavailable. Conversely, free web access does not prove CLI entitlement.

## Safe authentication

Install the official CLI through a verified package/distribution channel, then authenticate with:

```bash
grok login
```

Use the executable name `grok` in every command. The minimal headless smoke test is:

```bash
grok --no-auto-update -p "Say exactly: ok."
```

The CLI maintains its own credential state, currently under `~/.grok/auth.json`. Do not copy browser cookies, scrape web storage, print OAuth tokens, or treat a browser bearer as an API key. Never include the auth file in logs, prompts, commits, bug reports, or tool output.

## First verification

Run the smallest useful authenticated smoke test before changing Hermes configuration:

```bash
grok --no-auto-update -p "Say exactly: ok."
```

### Credential precedence check

Before interpreting the result, run `grok models` and read its authentication banner. If it says `You are using XAI_API_KEY`, the CLI is taking the direct billable API path even when `~/.grok/auth.json` exists. To verify subscription/trial OAuth, neutralize API routing variables only for that process:

```bash
env -u XAI_API_KEY -u XAI_BASE_URL grok models
env -u XAI_API_KEY -u XAI_BASE_URL grok --no-auto-update -m grok-4.5 \
  -p "Say exactly: ok." --output-format json
```

Require `You are logged in with grok.com` before claiming the CLI OAuth path is active. Do not delete or globally unset the user's API variables; process-scoped `env -u` avoids breaking unrelated xAI integrations.

For automation, prefer:

```bash
env -u XAI_API_KEY -u XAI_BASE_URL grok --no-auto-update \
  -p "<task>" --output-format json
```

When invoking programmatically, use the real command `grok`, set the project working directory, and pass `--no-auto-update`. Use `--always-approve` only when autonomous writes are explicitly intended; omit it for audits and reviews.

## Hermes routing choices

### Choose architecture from the requested UX

Distinguish these requests before editing Hermes:

1. **“Use Grok as a coding worker/agent”** → invoke `grok -p` directly or use ACP.
2. **“Use Grok like any other API model in Hermes”** → prefer a localhost-only OpenAI-compatible proxy backed by the authenticated Grok CLI, then configure Hermes as a custom endpoint with model `grok-4.5`.

For the second request, do **not** begin with a native ACP provider spread across Hermes internals. ACP provides agent semantics; the requested UX is ordinary model/provider semantics. A thin OpenAI-compatible proxy minimizes core changes, preserves authentication in the official CLI store, and fits Hermes' existing custom-provider path.

The proxy path is complete only after a real request succeeds **through Hermes itself**. An ACP `initialize` response or direct CLI smoke test is necessary evidence, but not end-to-end acceptance. Verify model selection, non-streaming output, streaming if advertised, timeout/error propagation, and process-scoped removal of `XAI_API_KEY` and `XAI_BASE_URL`.

See `references/openai-proxy-vs-acp.md` for the decision record and acceptance checklist. For the verified localhost adapter shape, supported `hermes config set` commands, port-collision handling, service lifecycle, and the final end-to-end probe, see `references/local-openai-acp-proxy.md`.

### Preferred for coding-agent work: direct CLI worker

Use the CLI as a separate coding worker when the requested UX is autonomous repository work:

- headless `grok -p` for one-shot tasks;
- PTY/TUI for interactive multi-turn work;
- `grok agent stdio` for ACP/IDE-style integrations;
- delegate through the existing autonomous-agent orchestration pattern when the task needs repository edits.

This path is robust because the official CLI owns authentication, sessions, tool permissions, and its protocol.

### Advanced: native ACP provider

Build a native ACP provider only when ACP-specific capabilities are genuinely required. When the active Hermes repository is dirty, use the isolated worktree procedure in `references/external-acp-provider-worktree.md`; unrelated local edits are a reason to isolate, never to abandon or overwrite the task.

For the **concrete code-level integration checklist** — the 7 files to touch,
exact changes per file, dispatch-table generalization pattern, pitfalls
(`replace_all` dead code, test import names), and verification commands —
see `references/acp-provider-code-checklist.md`.

The adapter should:

1. bind to localhost only;
2. translate only the request/response shapes Hermes actually needs;
3. keep credentials in the official CLI store or invoke the CLI, rather than copying secrets into a second config;
4. redact authorization headers and tokens from every log/error path;
5. implement timeouts, streaming behavior, cancellation, and a minimal health check;
6. pass an authenticated end-to-end smoke test before being exposed to Hermes.

Do not point Hermes' `xai-oauth` provider directly at `https://cli-chat-proxy.grok.com/v1`. Hermes' xAI OAuth resolver validates inference origins against `api.x.ai` / `*.x.ai`; the CLI proxy is a separate `grok.com` service and has a separate contract. A direct URL override either gets rejected or risks sending the wrong credential to the wrong service.

## Endpoint verification

For a read-only unauthenticated probe, the CLI service should respond with an authentication error rather than DNS/route failure:

```text
GET https://cli-chat-proxy.grok.com/v1/models
401 ... auth_kind=none ... no auth context
```

This confirms route existence only. It does not grant access and must never be “fixed” by guessing headers. Verify the authenticated contract through the official CLI or documented CLI protocol.

## Model naming

`grok-build-0.1` may appear in Hermes' curated xAI model list and in Grok configuration, but model-list presence is not an entitlement check and does not select the CLI backend. Confirm the actual backend and model accepted by the installed CLI version with a live smoke test; do not silently substitute `grok-4.5` or another model.

## Troubleshooting order

1. Check `command -v grok` and the installed CLI version.
2. Check login state without printing `~/.grok/auth.json`.
3. Run the minimal headless smoke test.
4. If it fails, classify the failure: entitlement/auth, CLI transport, tool approval, or repository/task issue.
5. Only after CLI success, integrate with Hermes or write an adapter.
6. If Hermes still returns `402`, inspect which base URL and provider actually handled the request; do not conclude that the CLI path is broken.

## Pitfalls

- Web access, Hermes xAI OAuth, and Grok CLI OAuth are not interchangeable.
- A direct xAI API spending-limit error is server-side billing, not a prompt or model-ID problem.
- Do not extract or proxy browser session cookies as a workaround.
- Do not expose a credential-bearing adapter on `0.0.0.0` or a public tunnel.
- Do not log raw upstream responses if they may contain authorization or account metadata.
- Treat undocumented CLI proxy endpoints as implementation-sensitive; prefer the CLI binary and verify every upgrade.

## Session-specific evidence

See `references/grok-cli-vs-xai-api.md` for the verified host distinction, authentication response, and integration decision record from the initial investigation.
