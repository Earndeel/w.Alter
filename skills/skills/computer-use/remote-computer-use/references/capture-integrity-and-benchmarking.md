# Capture integrity and benchmarking

## Purpose

Use this reference before tuning a remote Computer Use model, changing screenshot
resolution, or dispatching a GUI mutation. It is deliberately separate from the
class-level procedure because the measurements below are session-specific.

## Evidence from the 2026-08-05 VPS → Mac path

**MEASURED:** the legacy W.Alter Screen Server v5 was reachable through the SSH
forward on local port `18765`.

- `/health`: `status=ok`, `version=5`.
- Health round trip: approximately 226.7 ms.
- Five `/screenshot` calls: 413.0, 257.4, 272.0, 273.2, and 262.7 ms.
- Capture latency: median 272.0 ms, minimum 257.4 ms, maximum 413.0 ms.
- PNG payloads: 108,724–109,146 bytes; median 109,047 bytes.
- Image metadata: 2880×1800, PNG, RGBA.
- Visual inspection: only the Finder menu bar was visible; the rest of the
  frame was black. The capture was **not usable for Computer Use** despite a
  successful HTTP response and valid PNG metadata.
- One SSH process owned the local `18765` listener with
  `-L 18765:127.0.0.1:18765`; do not infer tunnel failure from the black frame.

**INTERPRETATION:** this is evidence of a capture-integrity failure, not evidence
that the vision model is poor. The leading diagnostic branches are the
permission-owning Mac process/TCC Screen Recording identity and the logged-in,
unlocked, awake GUI state. The exact cause remains UNKNOWN until the Mac-side
permission and session state are inspected.

## Required probe

Run a read-only probe before a model benchmark or mutation:

1. `GET /health` and record status/version/round-trip.
2. `GET /screenshot` once and record latency, dimensions, MIME, and bytes.
3. Calculate a cheap pixel signal (black-pixel ratio and/or luminance entropy).
4. Inspect whether the target app/window content is actually present. A
   menu-bar-only frame, uniform frame, stale frame, locked-screen frame, or
   empty scoped AX tree is invalid.
5. Stop before the LLM and before input if invalid. Do not retry a click against
   an invalid frame.

Do not use a byte threshold as the sole detector: a legitimate dark UI can be
small, while a black PNG can have plausible metadata. Combine pixel statistics
with a semantic/content check and, when available, scoped AX state.

## Remediation order when the frame is invalid

1. Check Screen Recording for the process that owns the Mac capture daemon;
   VPS permissions do not transfer across SSH.
2. Confirm the Mac GUI session is logged in, awake, and unlocked.
3. Restart the permission-owning daemon, then reconnect the SSH tunnel.
4. Repeat the read-only probe and require visible application content before
   allowing vision or input.
5. Only after this passes, benchmark models or change image scaling.

Do not solve a black capture by switching models, increasing retries, or
replaying an action. Those changes hide the fault and can turn an unseen click
into a real mutation.

## Model benchmark boundary

The following is the **vision leg only**, not a click-accuracy benchmark. Each
run used the same screenshot/prompt and a fresh Hermes CLI process; all expected
visual markers were returned:

- Gemini 3.1 Flash-Lite: median 13.357 s; runs 13.459, 24.164, 11.780,
  13.357, 11.229 s.
- Gemini 3.5 Flash-Lite: median 11.155 s; runs 78.182, 11.155, 11.051,
  10.983, 11.489 s. One severe tail outlier was observed.
- GPT-5.6 Luna through `openai-codex`, current Hermes reasoning configuration:
  median 12.761 s; runs 12.761, 13.041, 15.573, 12.164, 11.880 s.

Use these numbers only after capture integrity passes. For production Computer
Use, measure target-selection accuracy, postcondition success, false-success
rate, stale-reference handling, and p50/p95 end-to-end latency separately.

## Practical routing

- Prefer CLI/API/file operations for deterministic work.
- Prefer Camofox/Playwright/CDP for web-only work.
- Prefer AX/window state for native GUI state.
- Use scoped crops and Luna only for unresolved or consequential visual
  ambiguity; do not call a reasoning model on every passive frame.
- Always perform a fresh post-action verification and never replay a mutation
  after an unknown-completion timeout.
