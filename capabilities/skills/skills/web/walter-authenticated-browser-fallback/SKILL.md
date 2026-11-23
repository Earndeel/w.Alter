---
name: walter-authenticated-browser-fallback
description: "Use when Monsieur's existing Brave session does not authenticate a service and the task may need safe account fallbacks, Camoufox or Webtop browsing, or a visible Mac Brave W.Alter session."
type: workflow
requires: [authenticated-session-fallbacks, webtop-authenticated-browsing, mac-brave-walter]
---

# W.Alter Authenticated Browser Fallback

Run the stages in order, but stop as soon as the requested result is verified. The stages decide whether to continue; the sub-skills own the procedures. Start with the first-party URL, expected account, requested result or action, and any browser or visibility requirement. A named browser is a constraint: do not switch without approval.

Carry forward only what the next stage needs: the target URL, minimum account context, approved scope and browser, what was verified, and the exact blocker. Never pass cookies, credentials, tokens, or verification codes between stages. Use the current managed browser path for existing sessions, not legacy secret extraction instructions.

## 1. Classify the authentication failure

Load `authenticated-session-fallbacks` with `skill_read`. Establish whether the target is authenticated as the expected account. If not, use the approved sign-in or read-only fallback appropriate to the task. If an alternate source answers the request, finish and name that source without claiming the web session was restored.

**Check before handoff:** Pause if the account is ambiguous or if continuing requires a user identity challenge, new consent, or account recovery. Otherwise, if live browser access is still needed, pass the target, expected account, permitted browser surface, and the last verified page state to stage 2.

## 2. Try the approved remote browser

Load `webtop-authenticated-browsing` with `skill_read`. Use the managed existing-session path on the allowed Camoufox or Webtop surface. Check browser health, CDP connectivity, or the effective France exit as relevant to the request. Verify the actual target page and account before reading data or interacting; a healthy browser or initialized session does not prove sign-in.

**Check before handoff:** Finish if the task is verified. Otherwise distinguish a sign-in problem from a browser, route, or site-compatibility problem. Advance only if a Mac-specific browser requirement, a requested visible Mac session, or a W.Alter CDP recovery is relevant and permitted. If the site presents an access challenge, hand it to Monsieur rather than trying to bypass it. Pass the confirmed blocker, last verified page state, reason for switching, and unchanged account and scope to stage 3.

## 3. Use or recover the dedicated Mac browser

Load `mac-brave-walter` with `skill_read`. Use only the dedicated W.Alter instance. If CDP recovery is needed, verify that the recovered connection leads to that instance, not Monsieur's daily Brave. On the Mac surface, independently verify the target and account before resuming; do not assume authentication carried over. If user action is needed in the visible browser, pause and recheck the page after Monsieur confirms completion.

## Finish

Report the verified result and its source, or the exact blocker and what remains unknown. Do not treat a failed sign-in, route check, or browser connection as an empty result. Obtain confirmation before any unapproved external action, and clean up only temporary resources created by this run.
