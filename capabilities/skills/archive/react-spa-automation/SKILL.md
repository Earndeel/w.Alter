---
name: react-spa-automation
description: "Use when driving React SPAs: composers, chips, gates."
version: 1.0.0
author: W.Alter
license: MIT
triggers:
  - automate react app
  - composer chat input
  - type into spa
  - attach chip ingredient
  - approval gate button
  - send button does nothing
  - text disappears after typing
metadata:
  hermes:
    tags: [browser, automation, react, spa, composer]
    related_skills: [camoufox-max-api-current, web-service-browser]
---

# React SPA automation via DOM-driving browser APIs

Driving a React app through a browser HTTP API (evaluate, click-at, keyboard-type, snapshot refs) fails in repeatable ways because React state, not the DOM, decides what submits. Rules below are engine-agnostic; pair with the API-contract skill of the driver in use (e.g. camoufox-max) for endpoints.

## When to Use

Automating any React-built web app through a browser-driving API: chat/composer inputs (Flow, Gemini-style agent chats), wizard flows, attachment/ingredient pickers, in-app approval gates, submit buttons that silently no-op, or typed text that vanishes on re-render. Not for plain static pages — snapshot/click refs suffice there.

## Input entry

- Type with real key events (`keyboard-type` / `page.keyboard`) after a real click on the field. Setting `textarea.value` via the native setter plus an `input` event does NOT update React state: the next re-render (picker open, chip attach, route change) silently wipes the text and nothing submits.
- Never trust `querySelectorAll('textarea')` alone. React composers often keep hidden textareas beside the visible editable (`div[contenteditable=true]`, ProseMirror). A zero-rect hidden field silently accumulates text and looks like success. Probe bounding rects and target the visible editable (width > 100, y > 100, on-screen); verify the typed length on THAT element after typing.
- Verify typed length and attachment state immediately before the submit click — not right after typing, because the attach step can re-render.

## Clicks on dynamic elements

- Ref-based clicks (snapshot refs) go stale after any re-render and return errors even when a fresh snapshot re-issues a new ref for the same button. The reliable path on dynamic SPAs: probe the element's bounding rect with evaluate, then click at the rect center; re-probe immediately before clicking.
- An evaluate call returning an internal-error 500 usually means the expression failed to parse (regex/ternary slip), not that the browser or server broke. Simplify the expression before debugging infrastructure.

## Attachments and pickers

- Sequence matters: type the text first, attach the chip/ingredient second, submit immediately after. Attaching before typing invites a re-render that drops one of the two.
- A message with an attachment but no text may not submit at all (send silently no-ops). Always pair the attachment with prompt text and verify both (text length + chip presence) in the same pre-send check.
- Escape is destructive around chips: it dismisses the attachment even when the text survives. Close pickers by clicking the chosen item or elsewhere; press Escape only to dismiss plain menus, never between attach and submit.

## Submit and gate verification

- After clicking send, read the conversation/feed body for the new entry. An unchanged composer or an absent entry means the click was eaten (overlay, disabled button, swallowed event) — re-probe and retry, do not assume submission.
- In-app approval gates (credits, quotas, destructive actions) surface as conversation bubbles with decision buttons (e.g. Approve / Always approve / Decline). Match buttons by exact text equality — prefix matching grabs the wrong sibling ("Always approve" contains "Approve"). Click the per-case button, never the "always" variant, so each later spend keeps its human gate.
- A failure banner ("something went wrong") on a sent message does not mean the request died: the app may still process it and raise the approval gate afterwards. Do not re-send the prompt on a failure banner alone — re-read the conversation first for a gate or job state.
- A composer whose send icon flips to a stop icon means a job is in flight; wait and poll the conversation, do not stack new submissions.
