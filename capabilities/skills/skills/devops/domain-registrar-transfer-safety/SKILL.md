---
name: domain-registrar-transfer-safety
description: Use when transferring a domain registrar. Preserve DNS.
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [domains, registrar, cloudflare, hostinger, dns, transfer]
---

# Safe registrar transfers

## When to Use

Use for registrar transfers and associated DNS migration, access, pricing and continuity checks, especially Hostinger to Cloudflare.

## Access and scope

Treat registrar transfer, nameserver change, DNS migration and hosting cancellation as distinct operations. Do not cancel hosting or mail merely because a domain moves. Verify the actual checkout total and renewal extension within the owner's authorization; introductory registration prices are not transfer quotes.

Load walter-browse-orchestrator and use Walter Browse first. Use managed sessions for authenticated navigation. Never extract cookies manually or bypass a fail-closed managed network route using an unapproved authenticated bare-IP fallback. Distinguish infrastructure failure from an observed signed-out session: connection refusal and empty DOM prove neither bad credentials nor expired cookies.

Search credential metadata narrowly; no match does not prove an account does not exist. Never reveal EPP/auth codes, payment credentials, tokens or OTPs in conversation, logs, screenshots or reports. Use approved secret tools or server-side references. Never use a key known to be compromised as an authentication fallback.

An active Cloudflare token does not prove Registrar access. Verify account, zone visibility and Registrar endpoint separately. HTTP 403 / code 10000 means access blocked, not domain absent. An empty zone list proves absence only among zones visible to that token.

## Evidence before changes

Read authoritative RDAP: exact domain, registrar, expiration, EPP status, nameservers, registration date, secureDNS. Verify current official transfer requirements, registry/contact-change locks, receiving nameserver requirements and DNSSEC. An old registration date alone does not prove eligibility.

Export the COMPLETE source zone and relevant service settings before changing nameservers. Preserve names, types, values, TTLs, priorities, DKIM selectors, SRV, CAA, wildcards and provider-specific routing/flattening behavior. Inventory mail, certificates, redirects and hosting dependencies.

Public DNS queries and automatic scans cannot enumerate every record or unknown subdomain. When AXFR fails and the provider export is inaccessible, label observations incomplete and DO NOT switch nameservers from them. Query both authoritative servers and compare normalized answers without mistaking cache TTL changes for edits.

Check apex and www HTTP/HTTPS, TLS, redirects and real page title/content. HTTP 200 may serve a registrar parking page rather than a working shop. Report the observed content, not an assumed application.

## Execute and prove

Check current Cloudflare requirements; normally prepare and activate Cloudflare DNS before Registrar transfer. Import and compare every exported record before a nameserver switch. Preserve routing/proxy semantics rather than enabling proxying by default. Handle DS/DNSSEC changes in the correct order and verify propagation.

Unlock and request the EPP code only after prerequisites are satisfied. Keep the code server-side. Inspect the exact transfer total and extension before submitting within authorization. Expedite old-registrar approval only for the exact authorized domain.

Read back each changed target. Distinguish initiated, pending approval, pending registry, completed and failed. Verify dashboards, RDAP registrar/status/expiration, delegation, DNS and services. Preserve timestamped sanitized evidence and hashes. If blocked, state the exact step, errors, changes/charges initiated, and whether a complete zone backup exists. Do not claim successful migration when exhaustive backup/comparison was impossible; no DNS changes is the safe blocked outcome.
