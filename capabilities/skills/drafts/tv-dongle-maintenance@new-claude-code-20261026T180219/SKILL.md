---
name: tv-dongle-maintenance
description: "Use when the living-room Android TV dongle (D6, Stremio) is unreachable, asleep, slow, has no subtitles, or needs ADB/root work, debloat, restore, its KeepAlive service or raw HDMI-CEC."
---

# Living-room dongle: diagnose and maintain

Scripts and references live in the hub skill `android-tv-stremio-dongle`:
`D=$(walter path skills skills/media/android-tv-stremio-dongle)` → `$D/scripts/{stremio.py,restore.sh,cecsend.c}`,
`$D/references/{keepalive.md,debloat.txt}`. ADB runs from the Mac (`ssh mac`, adb in `/usr/local/bin`, key
already authorised): `adb connect 192.168.1.37:5555`, then `adb -s 192.168.1.37:5555 shell …`. Root: `su -c '…'`
works from the ADB shell without prompt.

**If Monsieur is watching** (`dumpsys media_session` shows `state=3` for `com.stremio.one`), touch nothing that
changes the screen: read-only commands only.

## Triage (in this order, ~1 min)

| Symptom | Check | Known cause → fix |
|---|---|---|
| `Dongle injoignable` / adb timeout | `ping 192.168.1.37` from the Mac; `adb connect` | Display asleep ≠ suspended ≠ rebooting ≠ unpowered: find which before saying why. KeepAlive service (below) keeps CPU + Wi-Fi up with the display off. If unpowered (TV cut USB power): only Monsieur can fix it; suggest an independent USB mains adapter |
| Reachable but the service is gone | `dumpsys activity services cloud.walter.tvkeepalive` → `isForeground=true`; `dumpsys power` → `PARTIAL_WAKE_LOCK walter:tvkeepalive` | Force-stop/uninstall disables it until relaunched: `am start -n cloud.walter.tvkeepalive/.StartActivity`. Install/rollback: `references/keepalive.md` |
| Film plays, **no subtitles** | `adb forward tcp:11471 tcp:11470` + `curl 127.0.0.1:11471/settings`; logcat `Failed to connect to /127.0.0.1:11470` | Stremio's local server is down: opening the player by deep link does **not** start it, opening Stremio's home does (~15 s cold; `stremio.py` does it before every launch). Keep Settings → Server → "Run in the background" **ON** (OFF = the server never starts) |
| Subtitles present but unreadable | Settings → Subtitles | Black opaque outline is the working setting; opacity moves 1 % per press |
| Stuttering / won't play | release in `tv-stremio-play` | 1 GB RAM: no HDR (washed-out), no AV1; ≤ 12 Mb/s average is the safe limit; HEVC/VP9/H.264 are hardware-decoded |
| Stremio stuck on a detail page after a launch | screenshot (`adb exec-out screencap -p`); `--state` shows no session (the activity name is the same for page and player) | The player link failed (seen with an uncached XviD release); `am force-stop com.stremio.one`, launch another release |

## The device (facts, verified 2026-10-26)

Chinese stick "D6" (`eros_p1`), Allwinner H313/H616 (`sun50iw9p1`), **1 GB real RAM** (reports 4 GB), 8 GB eMMC,
**Android 10 disguised as 12**, patch 2019-12, `userdebug`/test-keys, LAN `192.168.1.37`, ADB over Wi-Fi :5555.
Stremio `com.stremio.one` 1.11.x (ExoPlayer, hardware decoding) uses ~170 MB, ~100 MB stays free; 80–88 °C during
playback without throttling. HDMI outputs 4K60, UI renders 1080p. TV = Hisense 50A5FX (VIDAA), dongle on HDMI2.
**Untrusted device**: an always-root `su` daemon (`/system/bin/qw`, Koush Superuser) with SELinux permissive can't
be removed without modifying /system. No important accounts on it.

## Changes made to the dongle (undo everything: `sh $D/scripts/restore.sh [IP]`, reads `references/debloat.txt`)

- Adups FOTA removed for user 0 (`pm uninstall -k --user 0`: it restarts while merely disabled); ALD AppStore,
  KillAPP (`com.oranth.memoryclean`), `com.softwinner.update` disabled (all four had silent install/delete rights).
- 21 packages disabled (`references/debloat.txt`): unused apps, YouTube, Google voice assistant (71 MB),
  recommendations, factory-test and Miracast apps. Light launcher `com.gathin.tvhome` replaces Google TV's
  (78 → 33 MB). Animations 0.5. Caches trimmed (Stremio's had 1.1 GB).
- `hdmi_control_auto_device_off_enabled=1`; KeepAlive app `cloud.walter.tvkeepalive` (foreground `START_STICKY`
  service, CPU + Wi-Fi locks `walter:tvkeepalive`, starts at boot, device-idle exempt, no Internet permission);
  `stremio.py` also sets the legacy kernel lock `stremio_remote` (lost at reboot, kept as a fallback);
  `/data/local/tmp/cecsend`.
- `restore.sh` re-enables apps, Google TV Home, animations, CEC setting, removes KeepAlive and the lock. The light
  launcher stays installed and trimmed caches cannot come back.

## Raw HDMI-CEC

`/data/local/tmp/cecsend <dest hex> <bytes hex>…` (root). TV = destination 0. History: `dumpsys hdmi_control`
(`[S]` sent, `[R]` received). Power status: `cecsend 0 8F` → `[R] <Report Power Status> 04:90:00` (on) / `…:01`
(standby). Standby: `cecsend 0 36`. Internals: the sunxi driver `/dev/cec` takes ioctl `0xC0346305` on a 52-byte
struct (word0 = address of offset 0x0c, word3 = length incl. header, word4 = timeout ms, header byte at 0x20 =
`(4<<4)|dest`, body from 0x21), read from `hdmi_cec.cupid.so` `Hdmi2xCecDevice::transmit`. Rebuild (no Android
SDK): `zig cc -target arm-linux-musleabi -mcpu=cortex_a53 -static -Os -o cecsend cecsend.c` (official Zig
tarball, checksum from ziglang.org/download/index.json), then `adb push cecsend /data/local/tmp/` + `chmod 755`.

## What did NOT work: do not retry

- Input switching from VIDAA over CEC, Wake-on-LAN, Hisense MQTT, AirPlay pairing (details in `tv-power`).
- Disabling Adups FOTA instead of uninstalling it for user 0: it restarts.
- Turning "Run in the background" OFF to save RAM: the subtitle server then never starts.
- Asking Monsieur to wake the dongle with its remote after an ordinary reboot: the KeepAlive service restarts by
  itself (reboot tested); inspect service, locks, boot state and network first.

## Not tested yet

USB power loss and restore; overnight/multi-day stability of the KeepAlive service. Never disable thermal
protection to keep the stick running.
