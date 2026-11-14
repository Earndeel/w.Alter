---
name: evidence-and-execution-operations
description: "Use for evidence-backed software and operations work."
version: 1.0.0
author: Hermes Curator
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [evidence, records, approvals, delivery, meetings, administration, research, web, citations, mail, providers, llm, media, hermes, runtime, browser, auth, software-development, debugging, testing, frontend]
---

# Evidence and Execution Operations

Use this umbrella when software delivery, public-web research, messages, meetings, records, administrative forms, provider operations, Hermes runtime work, or other source material must become bounded evidence, a plan, or an approved, verified external action. Connector skills retrieve data; this skill owns evidence integrity, side-effect gates, and read-back. Choose the labeled branch that matches the task; use more than one branch only when a code change and an external operation are inseparable.

## When to use

Load this umbrella when a task crosses retrieval, provider or runtime execution, approval, or recipient-visible verification. Add a connector or API-specific skill for commands, but keep this skill's evidence, approval, and read-back gates.

## Always-on workflow

**Resolve sources → retrieve completely → normalize evidence → separate facts from proposals → reconcile contradictions → request approval → execute narrowly → read back.**

- Define account, tenant, identity, scope, time window, timezone, pagination, source authority, and permitted side effects before retrieval.
- Preserve source IDs, timestamps, speakers, documents, extraction method, confidence, attachments, and coverage gaps for every material claim.
- Keep observed facts, commitments, proposals, inference, unknowns, and compliance decisions distinct; use `unresolved` instead of inventing an owner, date, amount, or status.
- Search existing records before creating tasks, tickets, messages, or filings, because repeated workflows create duplicates and silent conflicts.
- Keep send, publish, spend, delete, archive, form submission, and other mutations behind explicit approval; scope approval to the named task and budget, and treat purchases or subscription changes as separate side effects. After any write or timeout, inspect provider state before retrying and read back the exact target.
- Keep secrets, signed links, OTPs, client data, and private attachments out of prompts, logs, durable notes, and final reports.

## Software delivery branch

- Freeze repository, branch or worktree, working directory, runtime, scope, role boundary, acceptance criteria, and verification commands before editing; preserve unrelated changes.
- Keep read-only audits and independent reviews non-mutating, and make every finding reproducible with a file, line, command, or artifact. For device diagnostics, preserve the initial power, display, network, and service state: inspect maintenance helpers before running them, because a status-looking helper may wake a display or reapply settings. Do not reproduce a power cycle, launch an app, inject input/CEC, restart ADB, enroll a key, or send a notification without separate authorization; carry the same boundary into delegated investigation. Report a bounded diagnosis rather than silently converting it into repair.
- For new behavior, bug fixes, and refactors, use RED → GREEN → REFACTOR: prove the test fails, make the smallest fix, then run focused and broader checks.
- For failures, inspect the complete error, reproduce only within the permitted side-effect boundary, compare a working analogue, and state one falsifiable hypothesis. Make one-variable changes only when intervention is authorized; otherwise use existing evidence and label untested hypotheses. Classify repeated failures and stop after three unchanged occurrences.
- Use a disposable spike only to answer a concrete decision, exercise edge cases, and record `VALIDATED`, `PARTIAL`, or `INVALIDATED`; do not promote the spike.
- Review complete diffs and wider-codebase reuse before cleanup; reviewers request changes rather than editing. Arm rollback before destructive deployment, use atomic swaps, restore exact bytes on failure, restart the owner, and verify functional loading.
- For external coding agents, isolate the repository or worktree, permissions, and spend limits; use bounded provider commands, inspect the complete diff, and run checks yourself because worker success never proves merge or delivery.
- For intake-driven work, persist validated required fields and do not advance while approval or revision gates are pending.

Read `references/software-delivery.md` for feasibility, test-first implementation, debugging, review, deployment, coding-agent, and intake depth, and `references/frontend-artifact-qa.md` for design and browser verification.

## Provider and model operations branch

- Resolve the exact provider, case-sensitive model ID, endpoint, API mode, region, account, modality, inputs, output contract, budget, and approval before changing a route or starting billable work.
- Check official catalog availability, account entitlement, permissions, quota, transport, active tool/schema exposure, adapter payload, provider execution, local tracking, artifact validity, and recipient access as separate gates. Authentication or a marketing name proves none of the later layers.
- Use the smallest non-billable contract probe through the intended client before spending. Classify validation, not-found, access, throttling, transport, execution, and artifact failures at the layer that produced their evidence; poll the original job after interruption instead of duplicating it.
- Compare providers with normalized prompts, inputs, tools, permissions, timeouts, budgets, and rubrics. Record latency, tokens, cost, errors, successful-task rate, and artifact quality separately, and label missing values.
- For media, bind real source bytes or provider handles and preserve hashes, dimensions, prompts, job/output IDs, and stage receipts. Keep generation, editing, captioning, audio, playback, and final delivery as separate gates; validate the downloaded artifact by metadata, full decode, visual/audio review, and brief compliance.

Read `references/provider-and-media-routing.md` for provider contract, evaluation, media-release, and browser-driven generation depth.

## Hermes runtime and authenticated-surface branch

- Freeze the active `HERMES_HOME`, profile, checkout, interpreter, config source, version, process owner, browser session, account or tenant, endpoint, and task identity before mutation; distinguish declared configuration, live health, effective behavior, rendered UI, and external outcome.
- Keep one canonical supervisor, browser session, and durable task identity. Serialize restarts, isolate profiles and auth stores, close temporary tabs or tunnels, and re-check the exact target after every write or ambiguous response.
- Keep passwords, tokens, cookies, OTPs, signed URLs, session databases, and private captures in protected stores or process memory. Pause writes behind the named human-intervention boundary, revoke input before resuming, and refresh identity, URL, tab, health, and target evidence.
- For a strict read-only audit of an existing session, freeze the permitted reads and output fields first. Use scoped session metadata or the exact existing local state before widening discovery; do not turn missing evidence into login recovery, browser restarts, network-route changes, content searches, playback, or download probes. Inspect a navigation or endpoint's automatic effects before treating it as a read.
- Project sensitive state inside the source-side process before any tool result: return only necessary canonical names, evidence labels, timestamps, and booleans. Keep raw session exports, addon transport URLs, credentials, passkeys, and personal content names out of tool outputs as well as the final answer; catch parsing failures without echoing input or exceptions containing it.
- Keep readable stored session state, a saved authentication field, access to a currently authenticated session, configured integration, and actual use as separate claims. Date snapshot evidence, label an untested current session as unconfirmed, and report absent markers as insufficient evidence rather than proof of absence. For a names-only audit, return only access status, relevant names, and their evidence level.
- Drive dynamic React surfaces through real visible interactions. Take a fresh semantic snapshot after rerenders, verify the visible field and attachment state immediately before submit, match exact per-case approval text, and poll an in-flight stop state instead of stacking submissions.
- A file reference is not delivery: verify authenticated byte access, MIME, disposition, Range support, client resolution, and recipient-visible playback or download separately. Never use `file://` for remote paths, never widen URL-token access to listings or text reads, and rebuild or restart the owner before claiming a renderer or server fix is live.

Read `references/hermes-runtime-and-surface.md` for runtime boundaries, strict existing-session audits (including Stremio's local addon schema), read-only Android/HDMI-CEC power diagnostics, browser handoffs, and media-delivery recipes.

## Public-web research branch

- Define the question, freshness boundary, source fields, sampling scope, and allowed access before fetching, because a page load or search result is not evidence by itself.
- Separate discovery, extraction, interaction, interpretation, and citation; preserve source IDs, URLs, timestamps, raw artifacts, and coverage gaps so claims remain auditable.
- Prefer canonical and primary sources, use the smallest useful fetch, and report blocked, stale, truncated, contradictory, or missing evidence instead of filling gaps.
- After a 403, 429, WAF, paywall, login wall, or bot interstitial, stop repeating the unchanged request; pivot through an authorized archive, same-host API/feed, or real browser and label snapshots with their date.
- Register sources while retrieving, cite while drafting, attach verbatim evidence for consequential claims, and verify that each citation resolves to the exact retrieved artifact.
- For monitoring, freeze entities, aliases, domains, event categories, cadence, cutoff, materiality, coverage, and deduplication keys; keep failed sources as explicit gaps and separate observed change from significance and confidence.

## Gmail mailbox-analysis branch

- Verify `users.getProfile(userId="me")` for every credential and keep each account's identity, token home, inventory, and findings separate, because a named address does not prove access.
- Request only `gmail.readonly` for analysis and use an account-specific OAuth home; never overwrite another account's token or silently broaden consent.
- Treat literal “all mail” as paginated coverage across labels with `includeSpamTrash=True` when requested, count returned IDs rather than estimates, and state the Spam/Trash boundary.
- Inventory IDs and metadata before fetching bodies, group messages by `threadId`, inspect complete relevant threads, and retain page, batch, and item failures as coverage data.

### Retention policy

- Retain healthcare records/results/appointments; active professional correspondence, applications, assessments, tasks, recruiter/vendor exchanges; administrative, tax/social-service, financial/account problems, upcoming travel, and personal correspondence. Preserve proof-bearing records after the immediate action when later evidence may matter.
- Treat routine merchant or ride receipts as noise only when they are not needed for a dispute, reimbursement, or accounting; apply the same default to spam, generic newsletters, promotions, job digests, webinars, and cancelled invitations. Do not infer importance from unread status.
- Keep importance analysis read-only. For approved cleanup, archive uncertain reference mail, trash clearly disposable noise, never permanently delete without explicit instruction, and read back exact provider state and counts, including exclusions.

## Inbox, meeting, and weekly branches

Classify inbox threads as urgent reply, reply, action without reply, waiting, reference, or noise, and draft in full thread context. For meetings, separate decisions, proposals, commitments, questions, blockers, risks, and context, then give actions explicit outcome, owner, due date, dependency, acceptance condition, and source. For recurring reviews, cover completed work and the planning horizon across calendars, tasks, notes, inboxes, and projects; reconcile waiting and stalled work before proposing a capacity-aware plan.

## Delivery branch

Treat call or message identity, route, destination, provider state, application completion, and recipient-visible success as separate layers. Use correlation IDs, idempotency keys, monotonic states, bounded retries, and explicit unknown outcomes. For telephony, inspect signaling, authentication, dialplan, RTP/media, codec, and application handoff separately; a 200 OK or queue acceptance does not prove two-way audio or recipient delivery.

- Treat artifact rendering and recipient retrieval as separate milestones: validate the final file, attach it through the platform's supported mechanism, and do not claim delivery from a backend path or attachment call alone. When Monsieur cannot download it, prioritize restoring access through a distinct authorized private route rather than renaming identical bytes or undertaking broad application repair. For an already authorized, reachable Mac, use a non-overwriting, byte-identical copy into Downloads and verify the exact destination; describe this as a delivery workaround, not a repaired chat button. Keep application download and creative approval unresolved until separately verified; read `references/hermes-runtime-and-surface.md` for the transfer recipe.

## Administrative filing branch

Use the exact supporting document and form jurisdiction before deriving values. Never invent or understate figures; preserve the source-to-field calculation, keep signatures and attestations truthful, use the correct flat-PDF overlay or form mechanism, and render the completed document to inspect alignment, overflow, and attachment coherence before delivery.

## Completion contract

Report covered sources and boundaries, evidence-backed findings, proposed versus completed actions, approval status, exact external write state, recipient-visible or document-visible verification, unresolved gaps, and anything still awaiting a gate. Immediately before closing, reconcile every reported status, amount, and completion milestone against the latest available primary-source readback; carry observed values forward accurately and label a value unavailable only when no readback exists.

Read `references/side-effect-branches.md` for delivery and administrative filing checklists; use `references/public-web-research.md` for research and citation depth, and `references/gmail-analysis.md` plus `scripts/gmail_readonly_oauth.py` for complete read-only Gmail inventory.
