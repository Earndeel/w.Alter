---
name: security-assurance
description: Use when verifying security controls or review evidence.
tags: [security, audit, authorization, credentials, evidence, verification]
metadata:
  hermes:
    tags: [security, audit, authorization, credentials, evidence, verification]
---

# Security Assurance

Use this class-level skill for read-only security reviews, authorization-boundary tests, credential-scope checks, and independent verification of review evidence.

## Review contract

Keep audits read-only, redact secrets, cite exact file and line evidence, classify severity, and label proof separately from suspicion. Start from the actual runtime and deployment target rather than assuming the checkout or a reviewer claim is authoritative.

## Fail-closed boundaries

Model an operation in pre-dispatch and post-dispatch phases. Fail closed before execution when policy, schema, approval, or intent recording fails. After the side effect has run, report completion as unknown or partially recorded when the closing audit/telemetry write fails; never relabel executed work as a pre-dispatch denial. Do not retry mutations without correlation/idempotency.

## Credential scopes

Keep catalog existence, local authentication, control-plane secret binding, build/dry-run, and deployed-runtime success as independent claims. A secret name proves presence, not value; a local 401 does not prove provider outage; a dry-run does not prove runtime auth. Require explicit approval before changed cloud code or billable remote smoke tests.

## Evidence integrity

Reproduce the stated verdict under the true runtime, compute hashes with the real interpreter, run the actual test suite, compare artifacts with their committed generators, and distinguish false positives from reproduced defects. A green claim is not evidence until the named suite ran; a schema claim is not evidence until the relevant artifact and runtime were checked.

## Verification

Test denial before dispatch, post-dispatch unknown completion, race/idempotence, credential layers, secret redaction, artifact/hash mismatch, and the actual review path. Report untested layers and unrelated failures explicitly instead of manufacturing a green result.

Exact historical audit, boundary, credential-scope, and evidence-reproduction procedures are routed in `references/curator-security-archive-routes.md`.
