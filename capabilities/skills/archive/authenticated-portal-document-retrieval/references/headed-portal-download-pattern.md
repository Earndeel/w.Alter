# Headed-Portal Download Pattern

## Observed pattern

A protected registrar portal stayed on Cloudflare's automatic verification page in headless mode. A separate headed Chromium profile on the webtop display cleared the challenge and redirected to a Keycloak-style identity-provider login page.

## Reliable sequence

1. Start headed Chromium with a separate temporary profile and CDP endpoint.
2. Navigate to the protected portal and wait for the identity-provider redirect.
3. Fill credentials from the vault without logging their values.
4. Wait for the portal to send a fresh email OTP; request that code from the user only then.
5. After submitting the OTP, wait for the SPA table to stop showing `Loading...`.
6. Open each row's details, trigger `Download`, capture the signed object URL in memory, and fetch it through the host-side process when the browser's download path is container-local.
7. Validate status, MIME type, byte count, and file signature before delivery.

## Evidence pattern

For the registrar portal used in the originating task, the authenticated table showed three rows for the same LLC: an initial resolution, an operating agreement, and a formation document. The portal's phone area showed an active phone line, but no explicit fax/dropbox label; related services must be reported separately rather than inferred.

## Security

Never print or persist passwords, OTPs, vault session keys, cookies, or complete signed URLs. Do not call a document "recovered" until the artifact exists at a host-visible path and passes validation.