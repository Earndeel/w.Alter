---
name: authenticated-media-generation
description: "Use when generating media via an authenticated web UI."
version: 1.0.0
author: W.Alter
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [authenticated-browsing, media-generation, browser-automation, artifact-verification]
    related_skills: [web-service-browser, webtop-authenticated-browsing, authenticated-session-fallbacks]
---

# Authenticated Media Generation

## Overview

Use this skill for media generation performed inside a logged-in web application rather than through a direct provider API. The reliable unit of work is not “click Generate”; it is a state machine that preserves the authenticated browser session, attaches the intended inputs, handles any model/credit confirmation, observes a real output identifier, downloads the binary through the authenticated context, and verifies the delivered artifact.

This is intentionally provider-neutral. Site-specific selectors, browser proxy routes, and quirks belong in `references/`; the always-visible rules below are the workflow and safety contract.

## When to Use

- A generation service is only usable through an authenticated browser UI.
- The task uses reference images, characters, scenes, audio, or other media inputs.
- The UI can consume credits or trigger a paid/billable generation.
- The final deliverable must be downloaded and validated, not merely shown as “complete.”

Do not use this as a substitute for a stable official API when the API is available and authorized. Do not treat a screenshot, a hidden `<video>` template, or a success toast as a verified media artifact.

## Operating Model

Treat the operation as four separate gates:

1. **Session gate** — the active browser context is authenticated and points at the intended project/tab.
2. **Input gate** — the prompt and every requested media input are attached to the same composer, in the intended order.
3. **Cost/action gate** — the service has not silently crossed a credit or account-permission boundary; explicit confirmation is handled before the billable action.
4. **Artifact gate** — a current media ID is fetched as a binary and passes container/metadata checks.

A later gate cannot compensate for an earlier one. A successful click before the cost gate is only preparation; a media URL before the artifact gate is only a candidate.

## Workflow

### 1. Establish and freeze the session identity

- Capture the browser backend’s active `userId`, `tabId`, and current URL.
- Verify the URL belongs to the intended project and the page is authenticated.
- Keep these identifiers together for all UI and binary-proxy calls.
- If navigation returns to a project list, obtain a fresh snapshot and open the actual project anchor; do not assume a card wrapper is clickable.

**Completion criterion:** the current tab is the intended project, authenticated, and the session identifiers are the ones used for the next action.

### 2. Treat accessibility refs as disposable

Browser automation layers commonly expose controls as refs such as `e123`. Any click, typing action, navigation, asynchronous rerender, picker transition, or agent response can invalidate them.

- Take a fresh accessibility snapshot after every state-changing action.
- Use the ref from that snapshot only once.
- When an action is a composite control, inspect the live DOM by exact visible text and use the current instrumented element.
- If a ref returns HTTP 400 or has no effect, do not retry it blindly: snapshot again and locate the new control.

**Completion criterion:** every action in the current step is backed by a ref from the immediately preceding state.

### 3. Fill the prompt and attach inputs

- Type the complete prompt using the current editor ref.
- Open the current media/input control.
- Select one input by exact filename or another stable identity.
- Wait for its selected preview, then invoke the current “add to prompt” action.
- Close or finish the picker, snapshot, and verify the resulting chip is in the same composer ancestor as the editor.
- Repeat one input at a time; never assume a batch of visible library cards equals attached inputs.
- Verify ordering with unique names or a stable preview. Keep the prompt’s `Image1`, `Image2`, etc. mapping aligned with the attachment order.

**Completion criterion:** the prompt is present and the composer contains one verified chip per requested input, in the intended order.

### 4. Gate the generate action

Before clicking the final generate/create control:

- Confirm every requested input chip is present in the composer.
- Confirm the prompt is not merely visible in a history/library panel.
- Confirm the live control is enabled (`aria-disabled="false"` or equivalent native state).
- If disabled, fix the input/state issue; do not force-click or invoke a hidden handler.

**Completion criterion:** the current generate control is enabled and the exact prompt/input state is recorded by live DOM or accessibility output.

### 5. Handle confirmation and billing deliberately

Many agent-style UIs use a two-stage flow: the first generate click prepares a request, then the agent asks for confirmation with a credit cost.

- Read the exact cost and scope from the current UI.
- Ask the user for authorization unless an applicable budget authorization already exists.
- For a one-time action, choose the one-time acceptance control.
- Never choose “approve and do not ask again” as a convenience; that changes future account behavior.
- Re-snapshot immediately before clicking the confirmation action because the agent response can rerender the whole composer.

**Completion criterion:** the user-authorized cost action has been clicked once, and the UI has moved from confirmation to generation/pending state.

### 6. Observe a real result

Poll the current project/media view rather than assuming completion from the click response.

- Look for a new media identifier, current media URL, playable media element, or explicit provider error.
- A hidden `<video>` with `readyState=0`, zero dimensions, or no duration is not yet a verified result.
- Distinguish old “failed” cards in project history from the current generation by correlating the current job/media ID.
- If an async browser evaluate returns `{}` for an async IIFE, split it into synchronous calls with explicit waits; `{}` can be a serialized Promise, not a successful operation.

**Completion criterion:** the current generation yields a concrete media ID/URL or a provider error that can be reported honestly.

### 7. Retrieve the binary through the authenticated context

Do not assume a media redirect URL is public. Use the browser session’s authenticated fetch/binary proxy when the service requires cookies or session headers.

Generic pattern:

```python
response = authenticated_tab_fetch_binary(
    user_id=user_id,
    tab_id=tab_id,
    url=media_url,
    timeout=300,
)
assert response.status_code == 200
with output_path.open("wb") as output:
    for chunk in response.iter_content(1024 * 1024):
        if chunk:
            output.write(chunk)
```

Keep provider-specific route names and request shapes in the linked reference, not scattered through the main skill.

**Completion criterion:** the output path exists, is non-empty, and the response content type matches the requested artifact.

### 8. Verify and deliver

For video, run `ffprobe` and check at least:

- container format and file size;
- duration against the requested duration;
- codec, width, height, and frame rate;
- audio stream when audio was requested.

Extract a frame with `ffmpeg` and inspect it when the scene, characters, or reference fidelity matters. Deliver the verified file path, not the transient browser URL. Report actual metadata and any mismatch; never invent a successful render.

**Completion criterion:** the artifact passes binary/container checks and, where relevant, a visual frame check before delivery.

## Common Pitfalls

1. **Stale refs after rerender** — snapshot after every action; a stale ref may no-op or target a different control.
2. **Clicking a decorative project wrapper** — inspect descendants and use the actual anchor/button.
3. **Visible library assets mistaken for attachments** — verify chips under the same composer as the prompt.
4. **Clicking while disabled** — repair prompt/input state and confirm `aria-disabled=false` first.
5. **Stopping after the first generate click** — agent UIs may still require a cost confirmation.
6. **Choosing persistent approval** — use one-time acceptance only unless the user explicitly wants future auto-approval.
7. **Counting a hidden video element as output** — require a media ID and a binary fetch with valid metadata.
8. **Fetching a protected redirect with unauthenticated HTTP** — route the download through the authenticated browser context.
9. **Retrying an async IIFE that returned `{}`** — split the sequence into synchronous evaluate calls; the result may be a Promise serialization artifact.
10. **Delivering without inspection** — run `ffprobe`, and extract a preview frame when visual identity is part of the request.

## Reference

- `references/google-flow-verified.md` — verified Google Flow/Camoufox Max sequence, confirmation wording, current binary-proxy route, and artifact checks.

## Verification Checklist

- [ ] Authenticated session and intended project/tab verified.
- [ ] Fresh refs used after every state change.
- [ ] Prompt and every requested input verified in the same composer.
- [ ] Generate control enabled before submission.
- [ ] Credit/cost confirmation handled with explicit scope and one-time acceptance.
- [ ] Current media ID/URL observed after acceptance.
- [ ] Binary fetched through the authenticated session.
- [ ] Container metadata and, where relevant, a preview frame verified.
- [ ] Final response points to the verified artifact and reports real metadata.
