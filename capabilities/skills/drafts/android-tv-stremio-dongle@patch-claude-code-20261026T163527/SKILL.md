---
name: android-tv-stremio-dongle
description: "Use when Monsieur asks to play a film or episode on the living-room TV, turn the Hisense TV on or off, or fix/maintain the Chinese Android TV dongle (Stremio, subtitles, ADB, HDMI-CEC, debloat)."
---

# Living-room TV: Android dongle + Stremio + Hisense over HDMI-CEC

Everything here was established and verified with Monsieur watching the screen on 2026-10-26. The TV only does what
he sees: a CEC message that was *sent* proves nothing. Check device/player feedback first (CEC power reply for the TV; player progress and selected tracks for playback).
Ask Monsieur about the screen only when remote evidence cannot establish the outcome. Verification follows the
requested action; it is not a reason to stop at the source list. Never report success from a sent command alone.

## The setup

| Thing | Facts |
|---|---|
| Dongle | Chinese stick "D6" (`eros_p1`), Allwinner H313/H616 (`sun50iw9p1`), **1 GB real RAM** (reports 4 GB), 8 GB eMMC, **Android 10 disguised as 12**, patch 2019-12, `userdebug`/test-keys. LAN `192.168.1.37`, ADB over Wi-Fi on 5555 (already authorised for the MacBook's `~/.android` key). Root: `su` works from the ADB shell without prompt. |
| TV | Hisense 50A5FX, VIDAA `V0000.09.09O.P1015`, LAN `192.168.1.36`. Dongle on **HDMI2** (CEC name "Living Room T"). TV setting **Default startup page = Last accessed source** (Monsieur set it; required). |
| Stremio | `com.stremio.one` 1.11.x, ExoPlayer, hardware decoding on. Addons: Torrentio, Torrentio TB, Comet/ElfHosted TB (TorBox debrid), WatchHub (legal offers), OpenSubtitles. Subtitles: English, black opaque outline. |
| Tools | `scripts/stremio.py` (search → rank → play, TV on/off), `scripts/cecsend.c` (raw CEC), `scripts/restore.sh` (re-enables every app, Google TV Home, animations, CEC setting, wake lock, KeepAlive service and cecsend; the light launcher stays installed and trimmed caches cannot come back), `references/debloat.txt`, `references/keepalive.md` (persistent Android service, APK/source backup and targeted rollback). |

The dongle and TV are on the home LAN. Run the tools from Monsieur's MacBook (needs `adb` and `python3`) or any host
on that LAN; from the Walter VM, only through a link to that LAN. Copy the scripts next to each other
(`stremio.py` pushes `cecsend` from its own folder).

## Daily use

From the skill folder (the folder holding `SKILL.md`):

```
python3 scripts/stremio.py "title" [--year Y]            # TV on (if off) + best source + English subtitles
python3 scripts/stremio.py "show" --s 12 --e 6           # analyse sources and play the best eligible one
python3 scripts/stremio.py "title" --lang fr              # explicit VF request
python3 scripts/stremio.py "title" --list                # ranking only, nothing launched
python3 scripts/stremio.py "title" --pick 3              # play the 3rd source of the ranking
python3 scripts/stremio.py --on                          # TV on (lands on HDMI2)
python3 scripts/stremio.py --off                         # TV off (even on the VIDAA home)
```

All options of `stremio.py`:

| Option | Effect |
|---|---|
| `"query"` | Title searched on Cinemeta (exact title first, else the most popular match; the alternatives are printed) |
| `--year Y` | Prefer Cinemeta matches released in Y (remakes, homonyms); if none matches, all results are kept |
| `--s N --e N` | Series: season and episode (episode defaults to 1) |
| `--lang vo` (default) / `--lang fr` / `--lang en` | Original audio by default; `fr` requires a VF candidate; `en` is an explicit English-audio request. The agent must verify and select the actual player track. MULTI alone proves no language. |
| `--original-lang CODE` | Known original audio language (ISO code); VO does not mean English. Do not invent it. |
| `--4k` | Legacy compatibility flag. Quality is now automatic: highest eligible resolution, with the same safety filters. |
| `--list` | Print the top 10 (score, resolution, size, cache/P2P, flags, addon) and launch nothing |
| `--pick N` | Launch the Nth source of the ranking instead of the first |
| `--open` | Open the title/episode page in Stremio, no source launched |
| `--on` / `--off` | TV power only (two separate commands) |
| `--host IP` | Dongle address (default `192.168.1.37`) |

From TV off to film on screen with subtitles: ~18 s (verified). Search + 4 addons + ranking: ~3 s.

## Owner's playback policy — updated 2026-10-26

Monsieur explicitly requests: analyse available sources, choose the best source adapted to the hardware, and
launch it. Default is **original audio (VO) with English subtitles**. Select **French audio (VF) only when he
explicitly asks for VF**. VO means the work's original language, not automatically English. If the work is French,
its original French track is VO. Do not silently substitute a dub or change his requested language.

This owner instruction supersedes the previous manual-selection requirement. Playback requests use the ranking
and player deep link by default. `--open` is reserved for an explicit request to browse or choose; `--list` for
inspection. Historical provenance note retained: the earlier skill described Torrentio/Comet results as
"unauthorised release rips"; availability through an addon does not establish authorisation. Do not claim otherwise.

1. Identify the exact film/year or series/season/episode. Use the current script from this skill, copying it to
   the LAN execution host before use so an older local copy does not retain the former French default.
2. Analyse candidates before launching. Hardware and requested language are constraints, then choose the highest
   suitable quality. The script rejects AV1, HDR/Dolby Vision, 3D, Remux, obvious CAM/TS, known wrong film years,
   unusable entries, and P2P with fewer than 10 reported seeds. These thresholds are operational heuristics.
3. Use size AND duration to estimate average bitrate, not size alone. Initial conservative limit: 12 Mb/s average
   (margin for peaks and Wi-Fi). Without bitrate information, reject files above 8 GB. These limits are not
   measured hardware ceilings. Do not increase them without a stable playback trial. For episodes, use episode
   runtime; a season pack's total size is not the episode size. If per-episode size is unavailable, choose a
   conservative individual release rather than treating the pack as measured.
4. Choose 2160p SDR HEVC when it has a direct link and known bitrate within the limit; otherwise descend to
   1080p, then 720p. Unknown codec/size/bitrate is uncertainty, not proof of compatibility. Prefer known
   compatible information; on unknown data use a conservative 1080p candidate. At equal resolution prefer
   cached debrid/direct availability and efficient HEVC. Check measured throughput with headroom when available;
   if throughput is insufficient, choose a lighter release. A cached marker is not a live speed test.
5. Launch the chosen stream directly, ensure the subtitle server is running, and select the actual audio track
   and English subtitles in the player (ADB/UI inspection as needed). VF labels and MULTI only identify
   candidates; verify the real French track for VF. For VO, establish the original language from reliable title
   metadata or the track list; do not infer English from a missing French label. Do not blindly edit undocumented
   preferences. Until tracks are confirmed, report them as unverified rather than saying VO/VF is configured.
   For an explicit VF request, keep English subtitles as the default unless Monsieur asks otherwise.
   **For VF, follow "Getting French audio (VF)" below**: the VF is chosen on the release title before launch,
   not fished for in the player afterwards.
6. Check actual playback progress and errors after launch, then a short stable playback interval. An Android
   intent acknowledgement, a player activity or audio focus alone does not prove video is playing. If startup
   fails or buffering persists, try another eligible source, favouring lower bitrate/direct cache and then lower
   resolution; keep the requested audio and subtitle language. Make at most three distinct attempts, identify
   failed releases to avoid repeats, and report the concrete blocker if none works. `--pick N` operates on a
   freshly retrieved ranking: inspect it and match the release before retrying. Never silently fall back to an
   incompatible format or a different dub. If no matching audio/English subtitles can be found, explain the
   missing item instead of pretending the request is satisfied.

The script automates candidate filtering, ranking and the launch request. Track selection, live throughput and
post-launch retries are the executing agent's steps above; they are not implemented by the score function.
Nine local selection tests and Python compilation passed on 2026-10-26. This revision has not been tested playing
a film on the dongle. The old ~18 s result above predates this revision.

## Getting French audio (VF)

Monsieur's rule (2026-10-26): **choose the VF before launching the stream, from the release title.** On a VF
request, the language is decided when you pick the source, not afterwards in the player.

**Why a MULTi release usually starts in English.** The Stremio profile on the dongle has
`settings.audioLanguage = "eng"` (read 2026-10-26 from `core.xml` → `profile`). When a file carries several audio
tracks, the player picks the track matching that language. A `MULTi.VFi` file whose French track is #1 still
plays in **English**. So "the title says MULTi" ≠ "VF is playing".

**1. Read the release titles** (`--list --lang fr`; the full label is in the stream `title`/`description`):

| Title tag | Audio | What to do |
|---|---|---|
| `TRUEFRENCH`, `VFF` (France), `VFQ` (Québec), `VF2` (VFF + VFQ), `FRENCH` **without** MULTi | French only (normally one track) | Best for VF: nothing to switch. Check that it is not VOSTFR (see below) |
| `MULTi`, `MULTi.VFF`, `MULTi.VFi`, `MULTi.VF2`, `DUAL` | French **and** original | Plays English by default (see above): the track must be switched. Plan for it |
| `VOSTFR`, `SUBFRENCH`, `vostfr` in the file name | **Original audio**, French subtitles | **Not VF**. Reject for a VF request (the addon's 🇫🇷 flag still makes the script show `FR`/"VF indiquée": seen on `S12E06.DSR.XviD-0TV.vostfr.avi`) |
| Only a 🇫🇷 flag / `FR` from the addon | Unknown | Uncertain: probe before launching |

At equal quality and compatibility, prefer a French-only release (no switch needed) over a MULTi one. Before
launching a lower-ranked one with `--pick N`, check the dongle can play it: on 2026-10-26 a `FRENCH DVDRiP XViD`
release (Comet, uncached `TB⬇️`, unknown resolution) never opened the player (Stremio stayed on the detail page),
while the cached MULTi.VFi HEVC release played. A failed player link can leave Stremio on the **next** episode's
detail page: check the episode before thinking a launch did something.

**2. Probe the tracks before launch when there is any doubt** (MULTi, flag only, missing tag). On the Mac (it has
`ffprobe` in `/usr/local/bin`), fetch the stream list for the id the same way `stremio.py` does (addons read from
`core.xml`), take the chosen stream's `url` and run
`ffprobe -v error -show_entries stream=index,codec_type,codec_name,channels:stream_tags=language,title:stream_disposition=default -of json "$URL"`
from a script. **Never print, log or put the URL in a command line you echo**: debrid/cached URLs embed the
TorBox/Real-Debrid key. Print only the track list. Verified example (2026-10-26):
`South.Park.S12E06.MULTi.VFi…TARDiS` → audio #1 `fre` "FR VFi : AC3 2.0", audio #2 `eng` "ENG VO : AC3 5.1".
A French-only file showed one audio track with no language tag: one track is enough proof for a `FRENCH` release.

**3. If the chosen file has several tracks, switch to French in the player.** Stremio remembers the switch per
title: `core.xml` → `streams.items[*][1].state.audioTrack = {"id": "0:2", "language": "fr"}` (seen 2026-10-26 on a
series Monsieur had switched himself). Once set, later episodes/launches of that title reuse it.
Player navigation (Android TV player, observed 2026-10-26 by screenshots; **not yet verified end to end**):
- `KEYCODE_DPAD_DOWN` shows the control bar without pausing; focus starts on **Play/Pause**. Observed button
  order: Play/Pause, Next episode, Rewind, Subtitles (CC), **Audio**, Speed, Fullscreen, PiP, Episodes.
- **Take a screenshot (`adb exec-out screencap -p`) after every key** and look at which button has the focus
  halo before pressing `KEYCODE_DPAD_CENTER`. CENTER on Play/Pause pauses the film (it happened); if
  `dumpsys media_session` shows `state=2`, press CENTER on Play/Pause again to resume.
- `uiautomator dump` returns nothing in the player (no accessibility nodes): use screenshots + vision, not UI XML.
- In the audio menu, select the French entry (label like "FR VFi"/"French"/`fre`), then BACK to close the menu.
- On a zsh host (the Mac), do not put the adb command in a variable (`$A KEYCODE…` fails: zsh does not split
  words). Write each `adb … input keyevent …` call in full, or use a loop.
Once this sequence is verified on a real MULTi playback, remove the "not yet verified" mention and record the
exact number of `DPAD_RIGHT` presses from Play/Pause to Audio.

**4. Verify, don't assume.** VF is confirmed when one of these holds: the file has a single audio track and its
release is French (step 1–2); or `streams` state shows `audioTrack.language = "fr"` for that title, re-read after
the switch; or a screenshot of the audio menu shows French selected. Playback progress alone says nothing about
the language. If none of these, report the audio as **unverified**.

**Do not** edit `core.xml` by hand (the app rewrites it, and its profile syncs to Monsieur's Stremio account).
Changing Settings → Player → default audio language to French would make every MULTi film start in VF, against
his default (VO); only do it if he asks, and say it is global.

## How the pieces work (when something breaks)

**Stremio without the UI.** Addon transport URLs (with the TorBox key: never print or store them) are read at every
run from `/data/data/com.stremio.one/shared_prefs/core.xml` → `profile.addons` via `su`. Search: Cinemeta
`/catalog/{movie|series}/top/search=<q>.json`; streams: `<addon base>/stream/<type>/<id>.json` in parallel (skip
`127.0.0.1` addons). Selection (`score()`): reject incompatible or excessively demanding sources before ranking. Highest eligible
resolution first (2160p 400, 1080p 300, 720p 200, 480p 100), then cached +30 / direct +15, HEVC +5,
explicit requested-language label +3, unknown bitrate −10. Original audio still needs track verification.
See the owner policy above for language constraints, bitrate/size limits and retries. Playback deep link, as in
stremio-core `Stream::encode`: `stremio:///player/{enc(zlib(json(stream)) → base64 standard)}/{streamTransport}/
{metaTransport}/{type}/{id}/{videoId}`, every part percent-encoded (keep `-_.!~*'()`). Detail page:
`stremio:///detail/{type}/{id}/{videoId}`. Launch with `am start -a android.intent.action.VIEW -d '<link>' com.stremio.one`.

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

**Persistent availability — installed and tested 2026-10-26.** The dongle must stay reachable even with the TV
or its display off. The initial live diagnosis showed `mLastSleepReason=hdmi`, with USB power still present;
this observation does not prove the cause of every reported outage.

The local Android app `cloud.walter.tvkeepalive` now runs a foreground `START_STICKY` service, holds a partial CPU
wake lock and high-performance Wi-Fi lock (both tagged `walter:tvkeepalive`), starts on `BOOT_COMPLETED` and
`MY_PACKAGE_REPLACED`, and is exempted from device idle. It does not wake the display or TV, has no Internet
permission, and requires no firmware modification or root for operation. See **references/keepalive.md** for the
signed APK/source archive in Raw Vault, install/verification commands, backup and targeted rollback.

Verified on the real D6: service and locks active; actual Android reboot (boot_id changed) with automatic service
startup and no manual relaunch; deliberate process kill followed by a new PID and reacquired locks after 12 s;
ADB plus both locks still active 20 s after `KEYCODE_SLEEP`. Display restored awake after tests. This is short
functional verification, not an overnight stability result.

`stremio.py` still writes the legacy kernel wake lock (`echo stremio_remote > /sys/power/wake_lock` via `su`)
when turning the TV on/off, opening a page or playing (not with `--list`). That lock alone is lost on reboot;
the Android service is the persistent replacement for depending on the next script run. Keep the legacy lock as
a secondary fallback. Do not require Monsieur to wake the dongle after every ordinary reboot: inspect the
service, locks, boot state and network first. A force-stop, disabling or uninstalling the app deliberately
disables its auto-start until it is explicitly launched again.

**Physical power remains a separate limit.** A software service cannot run or restart an electrically unpowered
dongle, recover a complete PMIC shutdown by itself, or guarantee recovery from a hardware hang. A real Android
reboot was tested; USB power loss/restoration was not. If the TV cuts USB power or its supply is unstable, power
the dongle from a suitable independent USB mains adapter and cable. Never disable thermal protection to keep it
running. Distinguish display asleep, system suspended, rebooting and actually unpowered before reporting a cause.

**Raw CEC** (`cecsend <dest hex> <bytes hex>…`, root): the sunxi driver `/dev/cec` takes ioctl `0xC0346305` on a
52-byte struct (word0 = address of offset 0x0c, word3 = length incl. header, word4 = timeout ms, header byte at 0x20 =
`(4<<4)|dest`, body from 0x21), read from `hdmi_cec.cupid.so` `Hdmi2xCecDevice::transmit`. Build (no Android SDK
needed): `zig cc -target arm-linux-musleabi -mcpu=cortex_a53 -static -Os -o cecsend cecsend.c` (official Zig tarball,
checksum from ziglang.org/download/index.json). The dongle's CEC history: `dumpsys hdmi_control` ([S] sent, [R]
received).

## Changes made to the dongle (undo: `sh scripts/restore.sh [IP]`; it reads `references/debloat.txt`)

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
- Automatically choose the highest eligible SDR quality using the owner policy; exclude Remux, HDR/DV and AV1. TorBox down → the plain Torrentio P2P addon is the fallback
  (Monsieur keeps it on purpose).
