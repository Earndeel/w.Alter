---
name: android-tv-stremio-dongle
description: "Use when Monsieur asks to play a film or episode on the living-room TV, turn the Hisense TV on or off, or fix/maintain the Chinese Android TV dongle (Stremio, subtitles, ADB, HDMI-CEC, debloat)."
---

# Living-room TV: Android dongle + Stremio + Hisense over HDMI-CEC

Everything here was established and verified with Monsieur watching the screen on 2026-10-26. The TV only does what
he sees: a CEC message that was *sent* proves nothing. When the outcome is visual (power, input, subtitles), ask him
what the screen shows or read the TV's CEC power reply; never report success from the sent log alone.

## The setup

| Thing | Facts |
|---|---|
| Dongle | Chinese stick "D6" (`eros_p1`), Allwinner H313/H616 (`sun50iw9p1`), **1 GB real RAM** (reports 4 GB), 8 GB eMMC, **Android 10 disguised as 12**, patch 2019-12, `userdebug`/test-keys. LAN `192.168.1.37`, ADB over Wi-Fi on 5555 (already authorised for the MacBook's `~/.android` key). Root: `su` works from the ADB shell without prompt. |
| TV | Hisense 50A5FX, VIDAA `V0000.09.09O.P1015`, LAN `192.168.1.36`. Dongle on **HDMI2** (CEC name "Living Room T"). TV setting **Default startup page = Last accessed source** (Monsieur set it; required). |
| Stremio | `com.stremio.one` 1.11.x, ExoPlayer, hardware decoding on. Addons: Torrentio, Torrentio TB, Comet/ElfHosted TB (TorBox debrid), WatchHub (legal offers), OpenSubtitles. Subtitles: English, black opaque outline. |
| Tools | `scripts/stremio.py` (search → rank → play, TV on/off), `scripts/cecsend.c` (raw CEC), `scripts/restore.sh` (undo all dongle changes), `references/debloat.txt`. |

The dongle and TV are on the home LAN. Run the tools from Monsieur's MacBook (needs `adb` and `python3`) or any host
on that LAN; from the Walter VM, only through a link to that LAN. Copy the scripts next to each other
(`stremio.py` pushes `cecsend` from its own folder).

## Daily use

```
python3 stremio.py "title" [--year Y]            # TV on (if off) + best source + English subtitles
python3 stremio.py "show" --s 12 --e 6 --open    # open the episode page, Monsieur picks the source
python3 stremio.py "title" --list | --pick N     # ranking only / play the Nth source
python3 stremio.py --on | --off                  # TV power
```

From TV off to film on screen with subtitles: ~18 s (verified). Search + 4 addons + ranking: ~3 s.

**Content rule.** Start playback yourself only for public-domain or legally offered content (WatchHub / Plex / free
sources). The Torrentio/Comet results are unauthorised release rips: for copyrighted titles use `--open` (or tell
Monsieur the command) and let him choose; do not auto-play them. Explain once, briefly, without lecturing.

## How the pieces work (when something breaks)

**Stremio without the UI.** Addon transport URLs (with the TorBox key: never print or store them) are read at every
run from `/data/data/com.stremio.one/shared_prefs/core.xml` → `profile.addons` via `su`. Search: Cinemeta
`/catalog/{movie|series}/top/search=<q>.json`; streams: `<addon base>/stream/<type>/<id>.json` in parallel (skip
`127.0.0.1` addons). Ranking prefers cached debrid (`[TB+]`, `⚡`) > direct > P2P by seeders; 1080p; FR/MULTI;
penalises HDR/DV/Remux/>25 GB and other-year files; excludes AV1 (no decoder). Playback deep link, as in
stremio-core `Stream::encode`: `stremio:///player/{enc(zlib(json(stream)) → base64 standard)}/{streamTransport}/
{metaTransport}/{type}/{id}/{videoId}`, every part percent-encoded (keep `-_.!~*'()`). Detail page:
`stremio:///detail/{type}/{id}/{videoId}`. Launch with `am start -a VIEW -d '<link>' com.stremio.one`.

**Subtitles need Stremio's local server** (127.0.0.1:11470: OpenSubtitles goes through `/subtitles.srt`). Opening
the player by deep link does NOT start it; opening Stremio's home does (~15 s cold). The script checks
`adb forward tcp:11471 tcp:11470` + `GET /settings` and opens the home first if needed. Symptom of a down server:
logcat `Disabling track due to error … Failed to connect to /127.0.0.1:11470`. Keep Settings → Server → "Run in the
background" ON (OFF stops the server from starting at all). If subtitles are present but unreadable, check the
outline colour/opacity (Settings → Subtitles; opacity moves 1 % per press).

**TV power over HDMI-CEC (what works / what does not, all verified):**

| Action | Works? |
|---|---|
| Dongle screen wakes (`input keyevent KEYCODE_WAKEUP`) → `<Image View On>` + `<Active Source>` | TV turns on, on HDMI2 thanks to "last accessed source" |
| `<Standby>` addressed to the TV (`cecsend 0 36`) | TV turns off, even on the VIDAA home |
| Broadcast `<Standby>` (dongle going to sleep) | Only obeyed while the TV is on HDMI2 |
| `<Give Device Power Status>` (`cecsend 0 8F`) | TV answers `04:90:00` when on (read `dumpsys hdmi_control`) |
| Switching input from VIDAA: `<Active Source>`, `<Set Stream Path>`, UI keys Input/Select/`69 02`, Home key (One Touch Play), repeated AS during boot | **No.** VIDAA ignores remote keys and source claims coming over CEC |
| Wake-on-LAN (dongle or TV), Hisense MQTT :36669 (needs the official app's client cert, not available on Android TV; Monsieur has no Android phone), AirPlay pair-pin-start (only shows a PIN on VIDAA) | **No / abandoned** |

**The dongle must never deep-sleep**: asleep, its Wi-Fi (ssv6xxx) goes dark and nothing wakes it remotely. The TV
keeps powering it by USB. The script writes a kernel wake lock (`echo stremio_remote > /sys/power/wake_lock` via
`su`) on every run, so the screen can sleep while ADB stays reachable. The lock is lost on reboot: after a power cut,
Monsieur wakes the dongle once with its own remote, then the next script run re-arms it.

**Raw CEC** (`cecsend <dest hex> <bytes hex>…`, root): the sunxi driver `/dev/cec` takes ioctl `0xC0346305` on a
52-byte struct (word0 = address of offset 0x0c, word3 = length incl. header, word4 = timeout ms, header byte at 0x20 =
`(4<<4)|dest`, body from 0x21), read from `hdmi_cec.cupid.so` `Hdmi2xCecDevice::transmit`. Build (no Android SDK
needed): `zig cc -target arm-linux-musleabi -mcpu=cortex_a53 -static -Os -o cecsend cecsend.c` (official Zig tarball,
checksum from ziglang.org/download/index.json). The dongle's CEC history: `dumpsys hdmi_control` ([S] sent, [R]
received).

## Changes made to the dongle (undo: `scripts/restore.sh` from its folder, same folder as `debloat.txt`)

- Adups FOTA removed for user 0 (`pm uninstall -k --user 0`; it is a persistent app that restarts while disabled);
  ALD AppStore, KillAPP (`com.oranth.memoryclean`), `com.softwinner.update` disabled. All four had silent
  install/delete rights.
- 21 packages disabled (`references/debloat.txt`): Monsieur's unused apps, YouTube, Google voice assistant (71 MB),
  recommendations, factory-test and Miracast apps. Light launcher `com.gathin.tvhome` (from the cleanyourtv repo)
  replaces Google TV's (78 → 33 MB). Animations 0.5. Caches trimmed (Stremio's had 1.1 GB).
- `hdmi_control_auto_device_off_enabled=1`, kernel wake lock, `/data/local/tmp/cecsend`.
- Not fixable without modifying /system: an always-root `su` daemon (`/system/bin/qw`, Koush Superuser) with SELinux
  permissive. Treat the stick as untrusted: no important accounts on it.

## Limits worth knowing

- 1 GB RAM: Stremio uses ~170 MB, ~100 MB stays free. No HDR (washed-out colours), no AV1. HEVC/VP9/H.264 are
  hardware-decoded; HDMI outputs 4K60, UI renders at 1080p. Runs 80–88 °C during playback without throttling.
- Prefer 1080p or 4K HEVC SDR; avoid Remux and HDR/DV. TorBox down → the plain Torrentio P2P addon is the fallback
  (Monsieur keeps it on purpose).
