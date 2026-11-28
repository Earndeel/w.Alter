---
name: hermes-operations
description: "Use for Hermes runtime, browser automation, auth, and file delivery into chat surfaces."
version: 1.0.0
author: Hermes Curator
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, runtime, authenticated, browser, react, spa, composer, computer-use, remote, sessions, media, file-delivery, attachments]
---

# Hermes Operations

Use this class-level umbrella for Hermes runtime state, authenticated automation, remote operations, browser sessions, file and media delivery into recipient surfaces, and durable Computer Use extensions. Keep identity, authorization, transport, persistence, rendered UI, and recipient-visible outcomes as separate evidence layers.

## Always-on rules

- Freeze the active `HERMES_HOME`, profile, checkout, interpreter, config source, version, process owner, browser session, and task identity before reading or changing state, because a correct operation on the wrong target is still a failure.
- Preserve exact provider/model IDs, endpoints, API modes, account and tenant identities, session lineage, and permission scope; never silently substitute defaults.
- Keep passwords, tokens, cookies, OTPs, signed URLs, session databases, and private screenshots in approved protected stores or process memory, because logs and prompts are not secret storage.
- Treat written configuration, live process state, transport health, persistence, client rendering, and external side effects as independent gates; a passing check in one layer does not prove the others.
- Prefer one canonical supervisor, browser session, and durable task identity; serialize restarts and close temporary tabs or tunnels in cleanup paths, because duplicate sessions create ambiguous state and leaks.
- Use the central approval and human-intervention boundary. Pause agent mutations under a manual lock, revoke input before resuming, and re-check target identity, URL, tab, health, and fresh evidence before releasing control.
- Keep custom Computer Use policy behind a narrow, named plugin or backend contract outside the core checkout where possible. Make extensions update-safe, fail closed on incompatibility, and never duplicate the host's schema, approval, lifecycle, or result plumbing.
- Distinguish transport acceptance, UI read-back, and task postcondition. A connected session, `verified` flag, process exit, or accepted API request is not proof that the requested user outcome occurred.
- Resolve remote host, cloud project, zone, service, and process owner before mutation; use the least-invasive authorized route, back up before repair, bind credential-bearing APIs to loopback or authenticated private routes, and remove temporary access after verification.
- After a state-changing operation, read back the exact target, re-check cleanup and session integrity, and report measured facts, observed code, risk, and unknowns separately.

## Runtime and profile branch

Keep profile-local skills, plugins, cron references, auth stores, session history, and derived memory isolated. Restart only the owner of changed code or configuration, then verify process identity, loaded configuration, endpoint, session continuity, and a real Hermes-path canary.

For a read-only profile assessment, follow `references/runtime-boundaries.md`; report configured state, live health, authorization/safety posture, prompt/tool footprint, and cross-profile findings as separate evidence layers.

## Authenticated browser and remote branch

Verify server flavor, port, endpoint contract, live browser, account, entitlement, and recipient route independently. Use fresh semantic snapshots after navigation or rerender, keep coordinate evidence bound to the newest capture and target geometry, and never expose browser control or media streams publicly.

## Durable Computer Use branch

Keep core approvals, action dispatch, session lifecycle, capture, and multimodal shaping in Hermes. Put target selection and named capture strategies behind a stable backend factory; test compatibility without performing a visible action; return explicit `no_target`, `needs_user_input`, or incompatibility states instead of guessing or silently falling back.

## React SPA automation branch

Drive React composers and dynamic controls through the browser's real interaction path, because React state—not a DOM value—determines what submits.

- Click the visible editable and type with real key events; reject hidden or zero-rectangle textareas, then verify the visible field's length immediately before submission.
- Expect refs to expire after rerenders; take a fresh snapshot or re-probe the target geometry immediately before each dynamic click. Simplify an evaluate expression after a parser-style internal error before diagnosing infrastructure.
- Type prompt text before attaching chips or ingredients, then submit immediately after verifying both text and attachment state. Close pickers by selecting or clicking elsewhere; do not press Escape between attachment and submission.
- Match approval buttons by exact text and choose the per-case action, never a broader always-approve variant. After sending, read the conversation for the new entry or gate; a failure banner alone is not proof that the job stopped.
- Treat a stop icon as in-flight work: poll the conversation or job state instead of stacking another submission.

## Media and file delivery branch

A `MEDIA:` tag or attachment is a reference, not a delivery. The recipient surface resolves it at view time, so bytes being served correctly proves nothing about the user seeing the file.

- Acceptance for a file deliverable is a **visible and playable/downloadable** item in the recipient conversation. An external player URL, a raw path, or a secondary surface is a fallback, never the deliverable — label it as one when you use it.
- Never hand the client a `file://` URL for a path that lives on a remote gateway: it is a dead link on the client machine and degrades silently into a dead "Open" button. Route it through the authenticated gateway download/stream route instead.
- Media elements (`<video src>`, `<audio src>`, `<img>`, `<a download>`) have no header channel. Every route they must reach has to accept the credential in the URL, and the query-token allowlist names it explicitly. Keep that allowlist to read-only byte delivery and leave listings and text reads header-only.
- Prefer a Range-capable streaming route for audio/video. A whole-file data URL is a size-capped, non-seekable fallback and silently drops larger media.
- Verify two layers separately: the bytes (MIME, Range, `inline` for playback vs `attachment` for download) and the client resolving the reference. Fixing one does not fix the other.
- A renderer change is invisible to a compiled client binary until it is rebuilt; a server change is invisible until its process restarts. State which one your fix needs before reporting it done.
- "Nothing appears in the conversation" localizes the fault: if the gateway log shows no client request at all for the media route, the failure is client-side reference resolution — not auth, size, or transport.

Read `references/media-delivery-chain.md` for the resolution chain and the symptom-to-cause table; `scripts/probe_media_routes.sh` re-runs the server-side byte-delivery and guardrail checks.

## Completion contract

Report the exact target identity, gates actually passed, external writes and read-backs, protected or missing data, artifact or session identifiers, cleanup state, and remaining uncertainty. Stop when authorization, backup, rollback, target identity, or completion evidence cannot be proved.

Read `references/runtime-boundaries.md` for the deeper branch decision tables.
