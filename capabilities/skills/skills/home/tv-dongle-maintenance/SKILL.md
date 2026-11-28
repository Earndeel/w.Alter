---
name: tv-dongle-maintenance
description: "Use when the living-room Android TV dongle (D6, Stremio) is unreachable, asleep, slow, has no subtitles, asks to be authorised again over ADB, changed IP, or needs ADB/root work, debloat, restore, its KeepAlive service or raw HDMI-CEC."
---

# Living-room dongle: diagnose and maintain

Scripts and references live in the hub skill `android-tv-stremio-dongle`:
`D=$(walter path skills skills/home/android-tv-stremio-dongle)` → `$D/scripts/{stremio.py,restore.sh,cecsend.c}`,
`$D/references/{keepalive.md,debloat.txt}`. ADB runs from the Mac (`ssh mac`, adb in `/usr/local/bin`). The dongle's
address is **not fixed**: find it first (below), then `adb connect <IP>:5555`, `adb -s <IP>:5555 shell …`. Root: `su -c '…'`
works from the ADB shell without prompt.

**If Monsieur is watching** (`dumpsys media_session` shows `state=3` for `com.stremio.one`), touch nothing that
changes the screen: read-only commands only.

## Find the dongle (do this before anything else, ~10 s)

1. The Mac's own address on the home LAN is `192.168.1.36` (`en0`, check with `ssh mac 'ifconfig en0 | grep inet'`).
   **That is the Mac, not the TV**: a ping to it proves nothing. The TV's address is unknown.
2. Sweep the LAN from the Mac, then look for the dongle by its services, not by its ARP entry (an ARP entry can be
   stale):
   ```
   ssh mac 'for i in $(seq 2 254); do (ping -c 1 -W 300 -S 192.168.1.36 192.168.1.$i >/dev/null 2>&1 &); done; sleep 8'
   ssh mac 'for h in 33 34 35 37 38; do nc -z -G 2 192.168.1.$h 11470 && echo "$h:11470 Stremio"; nc -z -G 2 192.168.1.$h 5555 && echo "$h:5555 adb"; done'
   ```
   Stremio's server (`:11470`, answers `curl http://IP:11470/settings`) is the sure sign of the dongle. Last known:
   **192.168.1.38** (2026-11-04; it was .37 before).
3. `stremio.py` defaults to `--host 192.168.1.37`: always pass `--host <IP found above>` to every call.

## Triage (in this order, ~1 min)

| Symptom | Check | Known cause → fix |
|---|---|---|
| `Dongle injoignable` / adb timeout / `No route to host` | Find the IP (above) — then `route -n get <IP>` on the Mac | **Mac VPN captures the LAN**: `route` goes through `utun` and adb says `Network is unreachable`. `ssh mac 'scutil --nc list'` shows the connected VPN (2026-11-04: WireGuard « Lucas »). Monsieur disconnects it or the route is wrong. Otherwise: display asleep ≠ suspended ≠ rebooting ≠ unpowered: find which before saying why. KeepAlive keeps CPU + Wi-Fi up with the display off. If unpowered (TV cut USB power): only Monsieur can fix it; suggest an independent USB mains adapter |
| `adb devices` shows `offline` or `unauthorized`, or `error: closed` | — | Connection state is flaky (seen 2026-11-04 for 15 min). Recipe: `adb kill-server; adb connect <IP>:5555; sleep 2; adb devices`, repeat until `device`. Then run the command at once (the state drops again after a few seconds) |
| `unauthorized` after a reboot-free period | — | The dongle forgot the Mac's key (`/data/misc/adb/adb_keys` rewritten, seen 2026-11-04 08:33 with uptime 16 h; cause not found). Monsieur must accept « Autoriser le débogage USB ? » on the TV and tick **« Toujours autoriser depuis cet ordinateur »** before OK, otherwise it asks again. Never regenerate `~/.android/adbkey` on the Mac, never « Révoquer les autorisations » in developer options |
| Reachable but the service is gone | `dumpsys activity services cloud.walter.tvkeepalive` → `isForeground=true`; `dumpsys power` → `PARTIAL_WAKE_LOCK walter:tvkeepalive` | Force-stop/uninstall disables it until relaunched: `am start -n cloud.walter.tvkeepalive/.StartActivity`. Install/rollback: `references/keepalive.md` |
| Film plays, **no subtitles** | `adb forward tcp:11471 tcp:11470` + `curl 127.0.0.1:11471/settings`; logcat `Failed to connect to /127.0.0.1:11470` | Stremio's local server is down: opening the player by deep link does **not** start it, opening Stremio's home does (~15 s cold; `stremio.py` does it before every launch). Keep Settings → Server → "Run in the background" **ON** (OFF = the server never starts) |
| Subtitles present but unreadable | Settings → Subtitles | Black opaque outline is the working setting; opacity moves 1 % per press |
| Stuttering / won't play | release in `tv-stremio-play` | 1 GB RAM: no HDR (washed-out), no AV1; ≤ 12 Mb/s average is the safe limit; HEVC/VP9/H.264 are hardware-decoded |
| Stremio stuck on a detail page after a launch | screenshot (`adb exec-out screencap -p`); `--state` shows no session (the activity name is the same for page and player) | The player link failed (seen with an uncached XviD release); `am force-stop com.stremio.one`, launch another release |

## The device (facts, verified 2026-10-26, IP updated 2026-11-04)

Chinese stick "D6" (`eros_p1`), Allwinner H313/H616 (`sun50iw9p1`), **1 GB real RAM** (reports 4 GB), 8 GB eMMC,
**Android 10 disguised as 12**, patch 2019-12, `userdebug`/test-keys, LAN address **changes** (`.37` until
2026-11-04, `.38` since; Freebox DHCP reservation = Monsieur's action), ADB over Wi-Fi :5555.
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
- Concluding "the dongle is off" from an ARP entry or from a ping to `192.168.1.36` (that is the Mac).
- Retrying `stremio.py` without `--host` after the dongle moved: it fails with `Dongle injoignable` even when the dongle is up.

## Not tested yet

USB power loss and restore; overnight/multi-day stability of the KeepAlive service; whether the ADB key survives
a dongle reboot (open since 2026-11-04). Never disable thermal protection to keep the stick running.
