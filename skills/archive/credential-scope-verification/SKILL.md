---
name: credential-scope-verification
description: Verify credentials across local, control-plane, and deployed-runtime scopes without conflating authentication failures with provider outages.
---

# Credential Scope Verification

Use this skill when an integration can obtain credentials from more than one scope: local vault, process environment, CI secret store, cloud control plane, or deployed runtime binding.

## Core principle

A credential check proves only the scope it exercised. Keep these claims separate:

1. **Catalog/endpoint** — the service and requested resource exist.
2. **Local authentication** — the credential resolved by the local process works.
3. **Control-plane configuration** — the deployment has a secret binding with the expected name.
4. **Deployed runtime** — deployed code can authenticate and complete the intended operation.

Never turn a local `401` or `403` into “the provider/model does not work.” State which authentication path failed and which paths remain untested.

## Workflow

1. **Identify the test scope before calling anything.** Record the credential source without reading or printing its value.
2. **Verify the resource independently.** Confirm the endpoint, model ID, API feature, or provider capability from its authoritative catalog/docs.
3. **Probe authentication narrowly.** Use the cheapest non-mutating or tightly bounded request available.
4. **Inspect control-plane metadata.** Confirm only the secret/binding name and deployment target; treat secret values as opaque.
5. **Verify the real runtime.** After explicit deployment approval, deploy the validated artifact and call a narrow remote smoke path that uses the deployed binding.
6. **Report each layer independently.** Include status, scope, HTTP result, and what remains unverified.

## Cloud/serverless rules

- A secret-list command proves presence of a binding name, not validity of its value.
- Local vault/env values and deployed secrets can diverge legitimately.
- Never retrieve, diff, log, or echo secret values.
- A successful dry-run proves bundling/config shape, not provider authentication.
- Deployment and billable provider calls require the user's applicable approval.

## Reporting template

- Resource/catalog: verified or failed.
- Local credential path: verified, failed with status, or untested.
- Deployment secret binding: present, absent, or untested.
- Deployed runtime call: verified, failed with status, or pending approval.
- Conclusion: precise scope; no provider-wide claim unless provider-wide evidence exists.

Prefer: “The local credential path returned 401; the deployed secret exists by name but has not been exercised.”

Avoid: “OpenRouter is broken” when only a local credential failed.

## Pitfalls

- **Credential-source ambiguity:** a helper may return a placeholder, masked value, or stale entry while the cloud secret is independent.
- **Control-plane overclaim:** secret metadata is not an authentication test.
- **Dry-run overclaim:** a bundle can compile while runtime auth still fails.
- **Outage overclaim:** distinguish invalid credentials, insufficient credits, unsupported model parameters, and actual provider availability.
- **Unsafe debugging:** do not print prefixes, suffixes, fingerprints, or raw values unless an established secure tool explicitly masks them.

## Verification

A verification is complete only when the user-requested runtime path has been exercised, or when a blocker is reported with the exact unverified layer. See `references/serverless-secret-scope.md` for a compact matrix and smoke-test checklist.
