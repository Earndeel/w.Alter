# Reference: remote wake-word feature triage

## Situation

The Desktop client runs on macOS while Hermes runs on an Oracle Linux VM. Manual voice triggering already worked through the existing STT path. The optional request was hands-free wake-word detection.

## Complexity discovered

The VM has no useful local microphone, so a durable implementation would have needed a client-side capture path plus a remote audio stream into the gateway, server-side buffering/decoding, detector lifecycle coordination, reconnect/cleanup behavior, and Desktop permissions. That is a distributed media feature, not a small wake-word toggle.

## Decision

Because the feature was expected to be used rarely, the manual trigger was the correct product decision. The wake-word relay was abandoned instead of adding a new JSON-RPC audio protocol and platform-specific capture code.

## Correct cancellation pattern

- Stop immediately when the user says the feature is not worth the hassle.
- Remove only code introduced by the canceled attempt.
- Verify the targeted diff is clean.
- Preserve unrelated modified and untracked files.
- Do not run a broad build/test cycle for work that was intentionally canceled.

## Lesson

For optional features crossing Mac ↔ VM boundaries, ask “is the manual path good enough?” before designing transport. A technically elegant relay is still the wrong solution when its maintenance surface exceeds the feature’s real usage.
