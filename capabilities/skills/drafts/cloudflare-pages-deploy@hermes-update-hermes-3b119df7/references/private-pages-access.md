# Preserve private access when moving a static site to Pages

Treat a private source as a prohibition on public upload, not merely on publicizing the resulting URL. An unguessable deployment URL is not an access control. If a private route cannot be proven, prepare the artifact locally and report the blocker instead of publishing it.

## Isolation and credentials

Resolve Cloudflare access through Walter Secrets. Use the installed `walter-cloudflare check` and `walter-cloudflare -- <command>` helper when available; it injects credentials without printing them. Verify current account, token scope and existing projects before creation. Wrangler supports global-key authentication with CLOUDFLARE_EMAIL and CLOUDFLARE_API_KEY; when deliberately using that route, unset an injected CLOUDFLARE_API_TOKEN for the child process so a less-privileged token does not take precedence. Do not expose credential values.

Snapshot the existing Pages project IDs, domains, canonical deployment IDs and existing Access application configurations before making changes. Create only the explicitly authorized isolated project, with production_branch set explicitly, no Git source or custom domain unless requested. Scope all writes to the new project and its newly created Access applications.

## Gate before confidential bytes

Cloudflare's built-in preview Access switch must not be assumed to protect the production project.pages.dev address. Follow the current official Pages preview/known-issues documentation and verify actual behavior.

A tested approach for an isolated direct-upload project is to create two account-level Access applications of type self_hosted, before uploading private files: exact `project.pages.dev` and wildcard `*.project.pages.dev`. Restrict each application to the explicitly authorized owner identity; set allowed_idps explicitly to the account's existing approved identity provider. With one-time PIN, allow only the owner's exact email, not everyone with an email or everyone with a Google account. Do not alter account-wide organization or provider settings.

Create the applications before the first deployment. Verify both application and policy readbacks. Deploy only a harmless canary first. Its files must contain no private site content, titles, source files or media. Probe the stable production URL, immutable deployment URL and branch alias with no cookies or credentials. Require an Access login redirect to the expected organization. Also test nested paths and asset paths: a home-page login alone does not prove assets are protected. If any anonymous probe returns canary bytes, stop; never upload private files while investigating the gate.

Authenticate against the canary and verify its expected bytes, rather than mistaking a login page or generic WAF denial for success. If unattended verification requires a service token, create a short-lived dedicated token and non_identity policies on these two new apps only. Reuse a still-valid verification credential rather than creating duplicate precedence-2 policies. Keep its secret in process memory or a mode-0600 file inside a mode-0700 scratch directory. Never print it. Inject verification headers only into the project's exact hostname and its subdomains; never into external-media requests. Do not request a human OTP just to run an automated canary test.

## Deploy and finalize

Freeze the exact source commit and static-export manifest. Require hashes of every staged file to match the requested commit before deploying, then pass the project name, production branch and commit metadata explicitly. A failed command or lost response requires a live canonical-deployment read before retrying; otherwise duplicate uploads or conflicting verification policies can result.

Verify the canonical deployment and exact commit through the API. Fetch every file while authenticated from stable and immutable URLs and compare cryptographic hashes with the manifest. Exercise the real deployed interface with a browser, including responsive layout, languages, media, controls and JS/HTTP errors. Keep external resource availability distinct from confidentiality: a private showroom does not make its already-existing public video URLs private, and those resources must not be moved or restricted without approval.

Revoke only the dedicated temporary policies and service token, read back their absence, verify the revoked credential no longer grants access, then remove the local temporary secret file. Confirm that only the intended owner policy remains on both applications. Repeat anonymous root, asset and nested-path checks against stable, immutable and branch aliases. Verify the visible login form without sending a code. Compare the original inventory against live state: existing projects, domain mappings, canonical deployments, Access apps and unrelated service inventories must remain unchanged.

Report the stable URL, private authentication method, requested commit, artifact/resource verification, untouched existing targets, and any limitations. Do not claim that the owner's actual login was exercised if only the login form and owner-only policy were verified.
