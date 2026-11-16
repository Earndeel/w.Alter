---
name: beeper-linux-arm-installation
description: Install Beeper Desktop on an ARM64 Linux server and prepare migration from a Mac without cloning active credentials or cryptographic device state.
version: 1.0.0
---

# Beeper Desktop Linux ARM64

Read the current instance and app layout first; packages belong under /apps/beeper, personal state under the instance (resolve with `walter instance path state/apps/beeper`). Read beeper-messages for the existing Mac integration. Do not change the Memory connector before the Linux instance is verified and coverage is compared.

## Official package

The official page https://www.beeper.com/download/linux exposes a `Linux (ARM)` link to https://api.beeper.com/desktop/download/linux/arm64/stable/com.automattic.beeper.desktop . Recheck the page because release details change. Use Walter Browse's normal download link; its fetch-binary interface is limited to Google media and must not be bypassed. On 2026-11-16 the ARM64 AppImage was Beeper 4.3.308. Verify ELF machine AArch64, completed download, record SHA-256 and source. Extract into a versioned release; keep the original and current symlink. The shipped extracted files include group/world writable modes: remove those write bits before deploying root-owned code.

## Service

Use a dedicated non-login account and a systemd service, with the official chrome-sandbox helper root:root 4755; run the binary as the dedicated user without --no-sandbox. AppRun may add --no-sandbox automatically when its unshare test fails; invoking the official executable directly allows an explicit sandbox choice. Provide the packaged usr/lib lookup if needed. Use a D-Bus session and an existing private X display or a separately approved desktop deployment; expose no new public desktop or API ports.

A systemd private bind of the instance app state into /run/beeper/home allows an account home without granting traversal of the rest of the owner's instance. PrivateTmp and the host X socket need compatible bind mounts. Keep UMask 0077.

**Create `.cache` before first start.** Also create the standard .config and .local/share directories with the application's owner. In this package, periodic updater code calls the native diskusage module on Electron's cache path. A missing cache directory caused `terminate called after throwing an instance of 'SystemError'` and repeated exit 134 about a minute after start. Creating the cache directory resolved the observed restart loop. Confirm stability over more than one updater interval; check service restarts and cgroup counters.

## Account

Sign in as a distinct Linux device using the existing account's confirmed email. Codes must be retrieved with Walter Secrets and filled locally without disclosure. Use `walter-python /usr/local/bin/walter-secret otp beeper ...` when the plain system interpreter cannot import the public Walter Memory Google client; consume stdout inside the local command, never return it to the model.

Beeper then requires existing-device verification or its recovery key. Do not assume a Bitwarden login's password is a recovery key: only submit a recovery key with confirmed semantics, or verify on an existing Mac/phone session. Never reset secure storage as a shortcut. Use the official instructions at https://help.beeper.com/en_US/quick-references/desktop-getting-started-guide . A logged-in but unverified account is not a completed migration.

Do not clone account.db, keychain contents, browser cookies or local bridge state while the Mac is active. Check each network and encrypted history after verification; local networks may require their own new-device connection. Keep the Mac and Memory connector until equivalence is demonstrated. Remove all temporary debugging listeners after setup. Do not send test messages without explicit authorization.
