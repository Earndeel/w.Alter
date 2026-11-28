---
name: mac-screen-to-browser-workflow
description: "Use when an authorized task starts with visible inspection or control of Monsieur's Mac, needs a verified SSH path from the VM, and continues in a browser where native tools are insufficient or a persistent Chromium session is required."
type: workflow
requires: [mac-computer-use-ssh, ssh-mac-remote-control, playwright-cdp-browser-control]
---

# Mac screen to browser workflow

Use the full chain only when the task needs all three stages. If a CLI or API can complete the task, or if native browser tools can handle a browser-only task, use that shorter path. Carry one task ID, the authorized target, and the expected result through every handoff.

## 1. Inspect the Mac and establish the starting state

Load `mac-computer-use-ssh` with `skill_read`. Use the existing screen connection to inspect the desktop before acting. Confirm the expected app or tab is present; before visible input, obtain task-scoped approval and recheck the target. Verify the effect of any input before moving on.

**Hand off to SSH:** the Mac identity, observed app or tab and expected URL, last confirmed action, and any reachability or permission blocker. If the screen connection is down, defer inspection to step 2 rather than guessing. If approval is denied, stop the affected action; do not move it to SSH or CDP to bypass the denial.

## 2. Verify or restore the remote path

Load `ssh-mac-remote-control` with `skill_read`. From the VM, confirm that SSH reaches the intended Mac over Tailscale. Reuse healthy forwards and repair only those the task needs. Verify both the remote identity and that each required forwarded endpoint responds as expected; a listening local port alone is not enough. If inspection was deferred or the connection changed, repeat the screen check before resuming. A working tunnel does not resolve a locked screen or missing macOS permissions.

**Hand off to CDP:** the verified browser connection path, whether it leads to Mac Brave or VM Chromium, the intended profile and tab, and the last confirmed task state. If CDP is not yet running, hand off the verified SSH path and mark browser readiness as pending. Use Mac Brave only when the task needs the actual Mac session; never use it for scraping or research. Do not switch profiles or hosts silently.

## 3. Continue in the verified browser session

Load `playwright-cdp-browser-control` with `skill_read`. Verify CDP readiness, then confirm the browser, profile, and exact tab URL before interacting. Ask before restarting or otherwise disrupting the user's browser. If the endpoint, profile, or tab does not match, stop and resolve the mismatch. Resume from the last confirmed state: after a disconnect or uncertain submission, inspect the current state before retrying. Preserve existing logins and hand user-only checks back to the user.

**Finish:** Verify the requested result in the browser, then report what changed or what remains blocked. Release any Mac control approval as soon as visible control is no longer needed and remove only temporary connections created for this task; leave existing sessions and persistent infrastructure intact.
