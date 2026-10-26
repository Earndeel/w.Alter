---
name: android-tv-stremio-dongle
description: "Use when Monsieur asks to play a film or episode on the living-room TV, turn the Hisense TV on or off, or fix/maintain the Chinese Android TV dongle (Stremio, subtitles, ADB, HDMI-CEC, debloat)."
---

# Living-room TV: Android dongle + Stremio + Hisense over HDMI-CEC

Everything here was established and verified with Monsieur watching the screen on 2026-10-26. The TV only does what
he sees: a CEC message that was *sent* proves nothing. Check device/player feedback first (CEC power reply for the TV; player progress and selected tracks for playback).
Ask Monsieur about the screen only when remote evidence cannot establish the outcome. Verification follows the
requested action; it is not a reason to stop at the source list. Never report success from a sent command alone.

## Fast path: play something (read this, then run; ~2 min end to end)

Run from the Walter VM. The script does the title search, the addons, the ranking, the track probe and the state
check itself: **do not query Cinemeta or the addons yourself, do not read `stremio.py`, do not write helper
scripts.** Read the sections below only if a step fails.

```
D=$(walter path skills skills/media/android-tv-stremio-dongle)
ssh mac "mkdir -p ~/walter-tv" && scp -q "$D/scripts/stremio.py" mac:~/walter-tv/   # always: refresh the Mac copy
ssh mac 'cd ~/walter-tv && python3 stremio.py "TITLE" [--year Y] [--s N --e N] [--lang fr] --list'
ssh mac 'cd ~/walter-tv && python3 stremio.py "TITLE" … --match "RELEASE-NAME" --probe'   # real tracks, nothing launched
ssh mac 'cd ~/walter-tv && python3 stremio.py "TITLE" … --match "RELEASE-NAME"'           # launch (wakes the TV)
ssh mac 'cd ~/walter-tv && python3 stremio.py "TITLE" … --state'                          # twice, ~10 s apart
```

1. **Identify the work** from Monsieur's words (episode described by its plot → find season/episode from your
   knowledge or one web search, then pass `--s/--e`). Same arguments on every call. VO is the default; add
   `--lang fr` only when he asks for VF.
2. **`--list`**, then choose a line per the policy below. For VF, read the release tags ("Getting French audio
   (VF)": French-only first, MULTi second, never VOSTFR; the script already rejects VOSTFR and ranks
   French-only releases ahead at equal quality).
3. **Designate that release by name with `--match`** (a distinctive part of its label, e.g. the group tag plus
   episode), for both the probe and the launch. Each call fetches a fresh ranking, so a rank (`--pick N`) can
   point to another release next time. Both commands print the release label they used: check it is the one
   you chose before trusting the result.
4. **`--probe` before launching.** It prints the real tracks and a verdict line.
   - **VF**: `VF OK` / `… déjà retenu le français` / `… conforme à la langue du profil` → launch. `… Basculer` /
     `… NON GARANTI` / `… INCERTAIN` → launch, then check and if needed switch the track in the player (VF
     section, step 3). `VF ABSENTE` / `VF NON PROUVÉE` → probe the next candidate.
   - **VO (default)**: the profile prefers English (`eng`), and VO is not always English. Establish the work's
     original language from reliable metadata (pass it with `--original-lang` when known), and compare it with
     the probed track list. If the original language is not English and an English track exists, the player is
     expected to start in English: switch the audio to the original-language track in the player (same player
     navigation as the VF section, step 3). If no original-language track exists, say so: never report a dub as
     VO.
   - P2P lines without a direct link cannot be probed: prefer a probed line, or report the audio as unverified.
5. **Launch with the same `--match`**, then **`--state`** twice: `en lecture` with a moving position = playing;
   it also prints the audio/subtitle tracks Stremio kept for this title. Report audio as verified only per the VF
   section's step 4 (for VO, the same evidence with the original language). English subtitles still need a
   screenshot (`adb exec-out screencap -p`) showing English text.
6. If it does not play: next eligible release (max three attempts, policy step 6).

Only `stremio.py` needs to be on the Mac for this path. Waking the TV uses `KEYCODE_WAKEUP` (no companion file).
`--off` uses `/data/local/tmp/cecsend` already installed on the dongle; the script would push a `cecsend` binary
from its own folder only if that file were missing, and the skill ships the source (`scripts/cecsend.c`, build in
"Raw CEC"), not a binary. No `export PATH` needed (the script adds `/usr/local/bin` for `adb`/`ffprobe`).
`--list`, `--probe` and `--state` never wake the TV. On zsh (the Mac) never store a command in a variable
(`$A KEYCODE…` fails).

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
| `--pick N` | Launch the Nth source of the ranking instead of the first (the ranking is recomputed at every call) |
| `--match TEXT` | Use the first eligible source whose label contains TEXT (release name) instead of a rank; works with `--probe` and the launch; exits without launching if nothing matches |
| `--probe` | With `--pick N`: ffprobe the Nth source on the executing host (Mac), print its video/audio tracks (language, title, default) and a verdict for the requested language, taking into account the track Stremio already kept for this title and the profile's preferred audio language. Launches nothing; never prints URLs (errors are masked) |
| `--state` | Player state from `dumpsys media_session` (playing/paused, position, title) and the audio/subtitle tracks Stremio kept for this title (`core.xml` → `streams`, episode first, else the series; else the profile defaults). Read-only. Does not prove English subtitles are on screen |
| `--open` | Open the title/episode page in Stremio, no source launched |
| `--on` / `--off` | TV power only, no film (two separate commands). `--off` also puts the dongle's screen to sleep (`KEYCODE_SLEEP`); it stays reachable over ADB (KeepAlive service) |
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
   freshly retrieved ranking: prefer `--match "RELEASE"` and check the printed label before retrying. Never silently fall back to an
   incompatible format or a different dub. If no matching audio/English subtitles can be found, explain the
   missing item instead of pretending the request is satisfied.

The script automates candidate filtering, ranking, the launch request, the audio-track probe (`--probe`) and
the playback/track state (`--state`). Switching a track inside the player, live throughput and post-launch
retries remain the executing agent's steps above. `python3 -I scripts/test_stremio.py` runs 22 local
tests (selection, VOSTFR rejection, French-only preference, probe verdicts incl. uncertain track choice, saved track, `--match`, URL masking); they
passed on 2026-10-26, and `--list`, `--probe` and `--state` were run read-only against the real dongle the same
day (probe ~2 s on a cached source). The old ~18 s result above predates these revisions.

## Getting French audio (VF)

Monsieur's rule (2026-10-26): **the VF is chosen when picking the source, from the release title, before
launching.** The player is never where the language gets decided. Picking a French-only release is the goal;
a MULTi release is a VF release too, but with the current Stremio setting it needs one extra confirmation step
after launch (below). That step applies the choice already made; it never replaces it.

**Why a MULTi release should start in English.** The Stremio profile on the dongle has `settings.audioLanguage
= "eng"` (read 2026-10-26 from `core.xml` → `profile`). When a file carries several audio tracks, the player is
expected to pick the track matching that language, even if the French track is first (Stremio's preferred-audio
setting; not yet confirmed by ear on the dongle). So "the title says MULTi" ≠ "VF is playing".

**1. Choose the release on its title** (`--list --lang fr`; the full label is in the stream `title`/`description`):

| Title tag | Audio | Use for a VF request |
|---|---|---|
| `TRUEFRENCH`, `VFF` (France), `VFQ` (Québec), `VF2` (VFF + VFQ), `FRENCH` **without** MULTi | French only (normally one track) | **First choice**: plays in French as is. Check it is not VOSTFR |
| `MULTi`, `MULTi.VFF`, `MULTi.VFi`, `MULTi.VF2`, `DUAL` | French **and** original | Second choice, when no playable French-only release of suitable quality exists. Requires step 3 |
| `VOSTFR`, `SUBFRENCH`, `vostfr` in the file name | **Original audio**, French subtitles | **Not VF**: reject. The addon's 🇫🇷 flag can still make the script show `FR`/"VF indiquée" |
| Only a 🇫🇷 flag / `FR` from the addon, no tag | Unknown | Probe (step 2) before choosing it |

A lower-ranked French-only release must still be playable on the dongle: on 2026-10-26 an uncached (`TB⬇️`)
XviD DVDRip with unknown resolution never opened the player while a cached HEVC MULTi release did. A failed
player link can leave Stremio on the **next** episode's detail page: check which episode is shown before
concluding anything.

**2. Probe the tracks before launch: `stremio.py … --lang fr --pick N --probe`** (same arguments as `--list`).
It runs ffprobe on the Mac against the Nth source and prints the tracks and a verdict line; no script to
write. Do not run ffprobe by hand on a stream URL: debrid URLs and addon transport URLs embed the
TorBox/Real-Debrid keys, and the script is what keeps them out of output. Verified 2026-10-26: a `MULTi.VFi` release gave audio #1 `fre` "FR VFi : AC3 2.0" and
audio #2 `eng` "ENG VO : AC3 5.1"; a `FRENCH DVDRiP` release gave a single untagged audio track (one track +
French release title is enough).

**3. MULTi only: make the player use the French track that was chosen.** Stremio stores the track per title in
`core.xml` → `streams.items[*][1].state.audioTrack` (e.g. `{"id": "0:2", "language": "fr"}`) and reuses it for
that title afterwards, so this is normally needed once per film/series (`--probe` then says "déjà retenu le
français"; that a kept track is reapplied on a deep-link launch is expected but not yet checked by ear). Player navigation (Android TV player,
observed 2026-10-26 on screenshots; **not yet verified end to end**):
- `KEYCODE_DPAD_DOWN` shows the control bar without pausing; focus starts on **Play/Pause**. Observed button
  order: Play/Pause, Next episode, Rewind, Subtitles (CC), **Audio**, Speed, Fullscreen, PiP, Episodes.
- **Screenshot (`adb exec-out screencap -p`) after every key** and check which button has the focus halo before
  pressing `KEYCODE_DPAD_CENTER`. CENTER on Play/Pause pauses the film (it happened); if `dumpsys media_session`
  shows `state=2`, put focus back on Play/Pause and press CENTER to resume.
- `uiautomator dump` returns nothing in the player (no accessibility nodes): use screenshots + vision.
- In the audio menu select the French entry (label like "FR VFi"/"French"/`fre`), then BACK.
- On the Mac (zsh) never put the adb command in a variable (`$A KEYCODE…` fails, zsh does not split words):
  write each `adb … shell input keyevent …` in full or loop over the keycodes.
Once verified on a real MULTi playback, remove "not yet verified" and record the exact number of `DPAD_RIGHT`
presses from Play/Pause to Audio.

**4. Verify, don't assume.** VF is confirmed when one of these holds: single audio track on a French-only
release (`--probe` says `VF OK`); `--state` shows the kept track `fr` for that title, re-read after step 3;
or a screenshot of the audio menu shows French selected. Playback progress says nothing about the language.
Otherwise report the audio as **unverified**.

**Do not** edit `core.xml` by hand (the app rewrites it and the profile syncs to Monsieur's Stremio account).
Changing Settings → Player → default audio language to French would start every MULTi film in VF, against his
default (VO): only on his request, and say it is global.

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
