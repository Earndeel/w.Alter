---
name: android-tv-stremio-remote-control
description: "Use when playing a title in Stremio on an Android TV box from a computer on the same network without using its UI, fixing missing Stremio subtitles, turning the TV on/off over HDMI-CEC, or auditing/debloating a cheap Android TV stick."
---

# Android TV box + Stremio + HDMI-CEC, driven from a computer

Procedures verified end to end on a cheap Allwinner stick and a Hisense VIDAA TV. Outcomes on a TV are visual: a
message that was *sent* proves nothing. Confirm power, input and subtitles by asking the person what the screen shows
or by reading the TV's CEC power reply; never report success from the sent log alone.

## Prerequisites

- `adb` and `python3` on a computer on the same LAN. ADB over Wi-Fi (port 5555) enabled on the box; the first
  connection needs "Allow USB debugging" accepted on the TV.
- Find the box: `dns-sd -B _adb._tcp local.` (macOS) then `dns-sd -G v4 <host>.local`, or the router's DHCP list.
  Never hard-code the address in shared files: `scripts/stremio.py` reads `--host`, `DONGLE_HOST` or
  `~/.config/stremio-remote/host`.
- Root (`su`) is needed for: reading Stremio's addon list, the wake lock, raw CEC. Many no-name sticks ship with an
  open `su`.

## Play a title without the UI (`scripts/stremio.py`)

```
python3 stremio.py "title" [--year Y]            # TV on if off + best source + playback
python3 stremio.py "show" --s 1 --e 3 --open     # open the episode page; the person picks the source
python3 stremio.py "title" --list | --pick N     # ranking only / play the Nth source
python3 stremio.py --on | --off                  # TV power over CEC
```

How it works, to repair or port it:

1. Addons come from `/data/data/com.stremio.one/shared_prefs/core.xml` → JSON `profile.addons` (root). Their
   transport URLs embed debrid keys: never print, log or store them. Skip `127.0.0.1` addons (unreachable from the
   computer).
2. Search Cinemeta `https://v3-cinemeta.strem.io/catalog/{movie|series}/top/search=<q>.json`; episodes use video id
   `tt…:season:episode` (titles/overviews are in `/meta/series/<id>.json` to find "the episode where…").
3. Query every stream addon in parallel: `<transport without /manifest.json>/stream/<type>/<videoId>.json` (~3 s).
4. Rank for weak hardware: cached debrid (`[TB+]`, `[RD+]`, `⚡`) > direct HTTP > P2P by seeders; prefer 1080p (or 4K
   HEVC SDR); penalise HDR/Dolby Vision (no HDR output on cheap sticks), Remux, files > 25 GB, files whose year
   differs from the title's (packs, sequels); exclude AV1 unless the SoC decodes it; bonus for the wanted audio
   language (VFF/MULTI…).
5. Launch the player directly. Deep link format from stremio-core `Stream::encode`:
   `stremio:///player/{E}/{streamTransportUrl}/{metaTransportUrl}/{type}/{id}/{videoId}` with
   `E = base64_standard(zlib(json(stream)))`, every segment percent-encoded except `A-Za-z0-9-_.!~*'()`.
   Detail page: `stremio:///detail/{type}/{id}/{videoId}`. Run `am start -a android.intent.action.VIEW -d '<link>'
   com.stremio.one`. If the app is already open on another screen, a deep link may only bring it forward: force-stop
   first when it matters.

**Content rule.** Start playback yourself only for public-domain or legally offered content (WatchHub/Plex/free
sources). For copyrighted titles that only resolve to release rips, use `--open` and let the person choose.

## Subtitles selected but not shown

Stremio routes OpenSubtitles through its local streaming server (`127.0.0.1:11470/subtitles.srt`). Symptom in
`logcat`: `Disabling track due to error … Failed to connect to /127.0.0.1:11470`. The server does **not** start when
the player is opened by deep link; opening Stremio's home starts it (~15 s cold). Check with `adb forward tcp:11471
tcp:11470` + `GET /settings`. Keep Settings → Server → "Run in the background" ON: turning it off stops the server
from starting at all. If subtitles render but are unreadable on bright scenes, set an opaque outline (Settings →
Subtitles → Outline colour; opacity moves 1 % per press: tap it in a loop on the device).

## TV power over HDMI-CEC

Read the CEC log with `dumpsys hdmi_control` ([S] sent, [R] received). Android playback devices send
`<Image View On>` + `<Active Source>` when their screen wakes (`input keyevent KEYCODE_WAKEUP`) and a broadcast
`<Standby>` on sleep when `hdmi_control_auto_device_off_enabled=1`. The Home key triggers One Touch Play.

Observed on Hisense VIDAA (expect similar smart-TV launchers to behave alike):

| Action | Result |
|---|---|
| Box wakes → Image View On | TV turns on |
| …and lands on the box's input | only with the TV setting **Default startup page = Last accessed source** |
| `<Standby>` addressed to the TV (raw `0x36` to address 0) | turns it off even on the TV's home screen |
| Broadcast `<Standby>` | obeyed only while the TV shows the box's input |
| `<Give Device Power Status>` (`0x8F`) | reply `90:00` on, `90:01` standby |
| Leave the TV's home screen via CEC: Active Source, Set Stream Path, UI keys (Input/Select/Select AV input), One Touch Play | **ignored**; fix the startup setting instead |
| Wake-on-LAN, AirPlay (`/pair-pin-start` just shows a PIN), Hisense MQTT :36669 (needs the official phone app's client certificate) | not usable for this |

## Keep a cheap stick reachable

Many sticks deep-suspend with the Wi-Fi off (cheap SDIO chips) and ignore Wake-on-LAN, so nothing remote can wake
them. If the TV keeps the USB power on, hold a kernel wake lock so the screen can sleep while ADB stays up:
`su -c 'echo <name> > /sys/power/wake_lock'` (check `cat /sys/power/wake_lock`; undo with `wake_unlock`). It is lost
on reboot: re-arm it on every run; after a power cut the box must be woken once with its own remote.

## Raw CEC on Allwinner (sunxi) boxes (`scripts/cecsend.c`)

Android 10 offers no shell command to send arbitrary CEC. The sunxi HAL (`/vendor/lib/hw/hdmi_cec.<board>.so`,
`Hdmi2xCecDevice::transmit`) writes `/dev/cec` with ioctl `0xC0346305` on a 52-byte struct: word0 = address of offset
0x0c, word3 = length incl. header, word4 = timeout ms, header byte at 0x20 = `(initiator<<4)|dest`, body from 0x21.
Verify on another board by disassembling the HAL (`llvm-objdump -d --triple=thumbv7-linux-gnueabi`). Build without
an Android SDK: `zig cc -target arm-linux-musleabi -mcpu=cortex_a53 -static -Os -o cecsend cecsend.c` (official Zig
tarball, checksum from ziglang.org/download/index.json); push to `/data/local/tmp`, run with `su`.

## Audit and debloat a no-name stick

- Real specs: SDK (`ro.build.version.sdk`) vs advertised Android; RAM from `su -c 'grep "System RAM" /proc/iomem'`
  (the `/proc/meminfo` total can be faked); storage from `/proc/partitions`; decoders in
  `/vendor/etc/media_codecs*.xml`; HDMI mode from `/sys/class/disp/disp/attr/sys` (root).
- Risks to report: `userdebug`/test-keys, old patch level, open `su` + permissive SELinux, FOTA apps such as Adups
  (`com.adups.fota`), preinstalled stores/"cleaners" holding `INSTALL_PACKAGES`/`DELETE_PACKAGES`, active connections
  (`/proc/net/tcp*` uid → `pm list packages -U`).
- Debloat with `pm disable-user --user 0` (reversible), never uninstall system apps; a *persistent* app restarts even
  disabled: `pm uninstall -k --user 0` (undo `cmd package install-existing`). Never disable core packages, the
  Settings app or the only Home; install a light launcher and start it before disabling the stock one. Save
  `pm list packages -f -U -i`, `getprop` and the disabled list first, and write a restore script alongside.
- For a 1 GB box the big wins are the stock launcher (~80 MB), the Google voice assistant (`katniss`, ~70 MB),
  trimming caches (`pm trim-caches 16G`; Stremio's torrent cache can fill the disk) and animations at 0.5.
