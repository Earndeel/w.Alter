---
name: mac-visible-control-over-ssh
description: "Use when Monsieur needs visible control of his Mac from the VM through the SSH screen server, including when the connection must be checked or repaired."
type: workflow
requires: [mac-computer-use-ssh, ssh-mac-remote-control]
---

# Mac visible control over SSH

Use this chain for an authorized task that requires inspecting or interacting with the Mac's actual desktop. If a terminal command or API can complete the task, prefer it. For SSH-only maintenance, use the SSH sub-skill directly.

## 1. Check GUI readiness

Load mac-computer-use-ssh with skill_read. Identify the intended Mac, target app or window, requested action, and expected result. Check the screen server and try a passive capture before sending any input.

If the capture is usable, verify that it shows the intended target and follow the GUI sub-skill's approval and verification rules. If the server is unreachable or an SSH session problem blocks the task, hand off the intended Mac, the connection or forward the GUI needs, and the failed check to step 2. A reachable server with an unusable capture is not by itself an SSH failure: handle screen state and permissions through the GUI sub-skill, asking Monsieur for help if needed.

## 2. Verify or restore SSH access if needed

Load ssh-mac-remote-control with skill_read. Verify that the VM reaches the intended Mac, then check or restore only the authorized session or forward needed for the task. Before handing back, confirm that the connection reaches the intended host and that the screen server responds through the required forward; a working SSH shell alone is not enough. Return the verified connection and service status to step 3, or stop and report the blocker if either check fails.

## 3. Resume and verify after a repair

Load mac-computer-use-ssh with skill_read. Take a fresh screenshot and recheck the target and current approval before any visible input. If the connection dropped during an action, inspect the current state before retrying: the action may already have landed. Stop if the target cannot be verified or approval is missing. On either path, verify the requested result, release visible control when finished, and report what was confirmed or what remains blocked.
