---
name: email-triage-preferences
description: "Use when triaging Monsieur's Gmail; apply retention rules."
version: 1.0.0
author: W.Alter
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Email, Gmail, Triage, Retention]
    related_skills: [email-inbox-triage, google-workspace]
---

# Monsieur's Email Triage Preferences

Apply these preferences as a calibration layer alongside the general inbox-triage procedure.

## Retain by default

- Keep medical records, laboratory results, healthcare-provider correspondence, and health appointments.
- Keep professional correspondence, active applications, assessments, tasks, and direct recruiter/vendor exchanges.
- Keep administrative notices, tax/social-service records, active financial or account problems, upcoming travel, and personal correspondence.
- Preserve documents in these categories even after the immediate action is complete when they may serve as proof later.

## Treat as noise when cleanup is approved

- Merchant receipts and routine transaction confirmations, including ride-hailing receipts such as Grab, unless they are needed for a current dispute, reimbursement, or accounting task.
- Spam, generic newsletters, marketing/promotional mail, generic job digests, webinars, and cancelled event invitations.
- Do not infer that an unread message is important merely because it is unread.

## Mutation boundary

- A question about what is important is read-only analysis; do not archive or trash messages until Monsieur approves a clearly described batch.
- When Monsieur approves cleanup, prefer archiving for uncertain reference mail and trash for clearly disposable noise; never permanently delete without explicit instruction.
- After any approved mutation, read back the provider state and report exact counts, including anything excluded.
