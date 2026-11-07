# TCC stale-process recovery on a remote Mac

Use this runbook when a remote Mac Computer Use screenshot is black or menu-bar-only even though Screen Recording is enabled in System Settings.

## Proven diagnostic sequence

1. **Separate capture from transport.** Check the tunneled health endpoint, capture through the HTTP endpoint, then run `/usr/sbin/screencapture` directly inside the Mac GUI user session. If both images are black, the HTTP server is only relaying a bad frame.
2. **Check the GUI session.** Confirm the console user is present and the display is not locked/asleep. `IOConsoleLocked=false`, `kCGSSessionOnConsoleKey=true`, and a non-empty console username are useful read-only signals.
3. **Inspect TCC identity.** Confirm the actual permission-owning process is enabled, not merely the terminal used to launch an older process. For a Python LaunchAgent, the Settings entry may appear as `python3`; cmux/Terminal grants do not prove that a different daemon process has refreshed its state.
4. **Restart the daemon before resetting permissions.** On the Mac, restart only the relevant agent:

```bash
launchctl kickstart -k gui/$(id -u)/com.walter.screen-server
```

Use the actual LaunchAgent label for another deployment. Reconnect the SSH client if it holds a persistent driver session.

5. **Run the capture-integrity gate again.** Require:
   - health endpoint reports `status: ok`;
   - PNG dimensions remain 2880×1800 for this Retina Mac;
   - the image is not a tiny black/menu-bar-only frame;
   - a semantic vision check sees real application content.

Do not use byte size as the sole test: a dark UI can legitimately be small or have a high black-pixel ratio.

## Verified acceptance example

During one incident, Screen Recording was already enabled for `python3`, `cmux`, and Terminal; the Mac session was logged in and unlocked. The old 2880×1800 screenshot was about 98 KB and visually black. After `launchctl kickstart -k gui/$(id -u)/com.walter.screen-server`, the next capture was 1.85 MB at the same dimensions and vision could read the Brave window. No TCC reset, model change, or permission toggle was required.

## Safety boundaries

- Do not reset the entire TCC database as a first response.
- Do not call the vision model or mutate the GUI while the capture gate is invalid.
- Do not infer that the model is at fault from a black screenshot.
- If the restart does not restore pixels, then investigate the permission identity, lock/sleep state, daemon executable, and macOS version before changing the model or adding retries.
