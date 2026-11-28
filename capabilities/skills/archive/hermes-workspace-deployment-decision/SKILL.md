---
name: hermes-workspace-deployment-decision
category: devops
description: Decide whether a custom domain should mirror the Hermes Workspace landing page or point to a real local Hermes Workspace install, and remember the gateway API pitfall.
---

# Hermes Workspace deployment decision

## When to Use
- User asks to deploy Hermes Workspace or a dashboard to a custom domain
- Ambiguous request between mirroring a landing page vs. running a real install
- Setting up a new domain for an existing Hermes instance

## Pitfalls
- Don't confuse proxying the public landing page with running the real local app
- The gateway API must be accessible from the domain — check firewall/tunnel config first
- Wrangler deploy may fail if the Worker name conflicts with an existing one on the account

---

Use when a user asks to put Hermes Workspace on a custom domain and the request is ambiguous between:
1. mirroring the public landing/setup site
2. installing and serving the real local Hermes Workspace app

## Core rule
If the user says anything like:
- install this dashboard
- I want this dashboard on my domain
- run the install script from my domain

then do NOT stop at mirroring or proxying the public landing page.
The intended outcome is usually the real local app, running on the machine, with the custom domain pointing to that local service.

## What went wrong in the failed path
A public-domain proxy of `hermes-workspace.com` can look correct at first, but it only delivers the landing/setup site.
That is not the same as a real installed Hermes Workspace instance.

## Reusable diagnostic question
Before finishing, verify which of these is true:
- "This domain shows the landing page"
- "This domain serves the actual local Hermes Workspace app"

If the user asked for installation, only the second is acceptable.

## Important technical pitfall
Hermes Workspace can appear installed but still be disconnected if the Hermes gateway HTTP API is not enabled.
The key requirement is that the local Hermes gateway exposes its HTTP API on the expected local port.

Practical lesson:
- if the frontend is up but backend health fails, check whether the gateway HTTP API is enabled before blaming the frontend
- on this setup, the missing piece was enabling the Hermes API server in the Hermes env/config so the workspace could talk to the backend

## Verification mindset
For this kind of task, verify all three separately:
1. the local app is actually installed
2. the local backend API is actually reachable
3. the custom domain is routed to the local app, not just to a mirrored marketing page

## Best practice
When the user’s wording is forceful or outcome-specific, optimize for the actual requested outcome, not the visually similar shortcut.
