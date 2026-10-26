---
name: android-tv-stremio-dongle
description: "Use when Monsieur mentions the living-room TV, the Hisense, Stremio or the Android TV dongle. Entry point: routes to tv-power, tv-stremio-play or tv-dongle-maintenance and holds their shared scripts."
---

# Living-room TV: start here

Pick the one skill that matches the request and read only that one:

| Monsieur wants | Skill | Time |
|---|---|---|
| TV on / off / "is it on?" | `tv-power` | ~10 s |
| A film or an episode, VO or VF | `tv-stremio-play` | ~2 min |
| Dongle unreachable, no subtitles, stutter, ADB/root, restore, KeepAlive, raw CEC | `tv-dongle-maintenance` | depends |

Each of them has a "what worked / what did NOT work" section: read it before trying anything new, it lists the
dead ends already paid for (2026-10-26).

## One-line commands (when you already know the procedure)

```
D=$(walter path skills skills/media/android-tv-stremio-dongle)
ssh mac "mkdir -p ~/walter-tv" && scp -q "$D/scripts/stremio.py" mac:~/walter-tv/   # always first
ssh mac 'cd ~/walter-tv && python3 stremio.py --on'                                 # / --off
ssh mac 'cd ~/walter-tv && python3 stremio.py "TITLE" [--s N --e N] [--lang fr] --list'
ssh mac "cd ~/walter-tv && python3 stremio.py \"TITLE\" … --match 'RELEASE' --probe"   # then without --probe
ssh mac 'cd ~/walter-tv && python3 stremio.py "TITLE" … --state'
```

## The setup

| Thing | Facts |
|---|---|
| Where to run | From the Walter VM through `ssh mac` (Monsieur's MacBook, on the home LAN; `adb`, `ffprobe` in `/usr/local/bin`, the script adds it to PATH). The VM itself cannot reach the LAN |
| Dongle | Chinese "D6", Android 10 (shown as 12), 1 GB RAM, `192.168.1.37`, ADB :5555 authorised for the Mac, root via `su` |
| TV | Hisense 50A5FX (VIDAA), `192.168.1.36`, dongle on **HDMI2**, setting "Default startup page = Last accessed source" (required for power-on on HDMI2) |
| Stremio | `com.stremio.one` 1.11.x. Addons: Torrentio, Torrentio TB, Comet/ElfHosted TB (TorBox), WatchHub, OpenSubtitles. Profile: audio language `eng`, subtitles `eng` auto, black opaque outline |
| Files here | `scripts/stremio.py` (everything below), `scripts/test_stremio.py` (local tests, `python3 -I scripts/test_stremio.py`), `scripts/cecsend.c`, `scripts/restore.sh`, `references/keepalive.md`, `references/debloat.txt` |

## `stremio.py` options

| Option | Effect |
|---|---|
| `"query"` | Cinemeta search (exact title first, else most popular; alternatives printed) |
| `--year Y` · `--s N --e N` | Disambiguate a film · series season/episode (episode defaults to 1) |
| `--lang vo` (default) · `fr` · `en` | VO by default; `fr` = explicit VF request (VOSTFR rejected, French-only ranked ahead); `en` = explicit English audio |
| `--original-lang CODE` | Known original language (VO is not always English); never invent it |
| `--list` | Top 10 eligible sources (score, resolution, size, cache/P2P, flags, addon, label); launches nothing |
| `--match TEXT` | Use the first eligible source whose label contains TEXT (stable across calls); exits if none |
| `--pick N` | Use the Nth source (ranking recomputed at every call: prefer `--match`) |
| `--probe` | ffprobe the chosen source on the Mac: tracks + verdict for the requested language; launches nothing; URLs masked |
| `--state` | Player state (playing/paused, real position computed from the `updated` snapshot, title playing) + audio/subtitle tracks Stremio kept for this title; read-only |
| `--open` | Open the title/episode page, no source launched |
| `--on` / `--off` | TV power (`--off` also sleeps the dongle screen; ADB stays up) |
| `--host IP` | Dongle address (default `192.168.1.37`) |

`--list`, `--probe`, `--state` never wake the TV. Launch, `--open`, `--on/--off` set the legacy kernel wake lock.

## How it works (for fixing the script)

- Addon transport URLs (they embed the TorBox key: never print, log or store them) are read at every run from
  `/data/data/com.stremio.one/shared_prefs/core.xml` → `profile.addons` via `su`. Same file: `profile.settings`
  (audio/subtitle language) and `streams.items` (per-title kept tracks).
- Search `…/catalog/{movie|series}/top/search=<q>.json`; streams `<addon base>/stream/<type>/<id>.json` in
  parallel (127.0.0.1 addons skipped). `score()` rejects what the dongle cannot play, then ranks: resolution
  (2160p 400, 1080p 300, 720p 200, 480p 100), cached +30 / direct +15, HEVC +5, language label +3, French-only +4
  for VF, unknown bitrate −10.
- Player deep link as stremio-core `Stream::encode`: `stremio:///player/{base64(zlib(json(stream)))}/
  {streamTransport}/{metaTransport}/{type}/{id}/{videoId}`, each part percent-encoded (keep `-_.!~*'()`);
  `am start -a android.intent.action.VIEW -d '<link>' com.stremio.one`. Detail page:
  `stremio:///detail/{type}/{id}/{videoId}`.
- Before a launch the script makes sure Stremio's local server (127.0.0.1:11470, subtitles) answers, opening the
  home screen if needed (a deep link alone does not start it).
- `dumpsys media_session` `position` is a snapshot at `updated` (elapsedRealtime ms); `--state` adds
  `(nowELAPSED − updated) × speed` from `dumpsys alarm` (raw 12:12 vs computed 38:43 on 2026-10-26).
- Tests: 22 local checks (selection, VOSTFR, French-only preference, probe verdicts, kept track, `--match`,
  URL masking). `--list`, `--probe`, `--state` were run read-only on the real dongle on 2026-10-26.
