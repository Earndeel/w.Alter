# Private Cloudflare Pages: prove the gate before publishing

Use this branch when an existing artifact is private or publication approval is explicitly private-only. A new Pages project is public by default; an unguessable deployment URL is not privacy.

## Freeze the scope

- Pin the exact source commit, export directory, source-file hashes and project name. Keep source files unchanged for a deployment-only request; compare an isolated rebuild with the committed export where reproducible.
- Snapshot the existing Pages project/domain inventory and Access application configuration before creating the isolated target. Do not change existing projects, custom domains, DNS or account-wide identity providers merely to deploy a separate showroom.
- Obtain credentials through the installed Walter Secrets execution wrapper. Keep credential values out of tool output, command-line arguments, logs and deployment files.

## Establish Access before private bytes

- Where the account accepts self-hosted Access applications for Pages hostnames, create separate scoped applications for `project.pages.dev` and `*.project.pages.dev`. The wildcard covers immutable deployment and branch aliases but does not cover the apex project hostname.
- Use an explicit owner-email allow rule and the existing approved identity provider. Do not use `everyone`, broad email-domain allow rules, bypass policies or a global Access organization change. Read back each exact application and policy.
- Do not equate the built-in preview-protection switch with protection of production. Publish only a harmless canary first, after creating the gate, and test production, immutable and branch URLs and direct resource paths without credentials. Require the expected Access redirect or denial; never infer protection merely from an API success.
- Also prove an authenticated fetch of the canary. If any route is public or authorized access cannot be demonstrated, do not upload the confidential export. Preserve the prepared artifact and report the blocker.

## Authenticate automation without leaking the credential

- When needed, create an explicitly short-lived service token and narrowly scoped temporary service-auth policies only on the newly created applications. Cloudflare's API represents service-auth decisions as `non_identity` and token selectors as `{"service_token":{"token_id":"..."}}`.
- Hold the returned client secret only in process memory or a mode-0600 file in a mode-0700 task directory. Never print the token response.
- Inject `CF-Access-Client-Id` and `CF-Access-Client-Secret` only for the exact protected project hostname and its deployment subdomains. Do not set global browser headers: external media requests would receive the secret. Use per-request hostname checks and isolated disposable browser contexts.

## Publish, verify, revoke

- Upload only the pinned export to the explicit new project and production branch. Read back the exact deployment and canonical project pointer before claiming production changed.
- Compare every static-file hash on stable and immutable URLs while authenticated. Normalize Pages HTML canonical redirects when selecting the fetch path. Run real desktop, mobile, language and reduced-motion checks; use instant scroll for deterministic scroll-phase assertions rather than racing smooth scrolling.
- Remove the temporary service-auth policies and revoke the temporary token after verification. Read back each deletion and owner-only rule, and prove that the old credential is rejected before deleting its local temporary file. Make cleanup idempotent or split final read-only verification from mutation, so a later UI assertion cannot require recreating an already revoked credential.
- Repeat anonymous resource probes after cleanup. Observe the login page in a fresh uncredentialed browser; verify the email/code UI without sending a code unless authorized. Derive action labels from the current DOM rather than inventing exact button text. An automated service-token test does not establish completion of the owner's email-code sign-in.
- Compare the pre-existing project/domain and Access inventories with the original snapshot. Keep a durable redacted receipt with commit, deployment ID, URLs, hash checks, access checks, cleanup and coverage boundaries.
- List pre-existing public external-media dependencies separately. Protecting the new Pages bundle does not privatize assets on another existing host, and deployment-only approval does not permit changing that host.
