---
name: tv-stremio-play
description: "Use when Monsieur asks to put on a film or a series episode on the living-room TV (Stremio on the Android dongle), in VO or VF. Search, pick the right release, check audio tracks, launch, verify; ~2 min."
---

# Play a film / episode on the living-room TV

Monsieur's request: analyse the sources, pick the best one the dongle can play, launch it. **Default = original
audio (VO) + English subtitles. VF only when he asks for VF.** VO means the work's original language (a French
film's VO is French). The sources are those of his own Stremio addons; launching is what he asked for.

The script does the search, addons, ranking, track probe and state check. **Do not** query Cinemeta or the
addons yourself, **do not** read `stremio.py`, **do not** write helper scripts: each of these cost earlier runs
several minutes (MiMo run 2026-10-26: 10 min instead of ~2).

```
D=$(walter path skills skills/media/android-tv-stremio-dongle)
ssh mac "mkdir -p ~/walter-tv" && scp -q "$D/scripts/stremio.py" mac:~/walter-tv/   # always: refresh the Mac copy
A='"TITLE" [--year Y] [--s N --e N] [--lang fr]'                                     # same arguments every call
ssh mac "cd ~/walter-tv && python3 stremio.py $A --list"
ssh mac "cd ~/walter-tv && python3 stremio.py $A --match 'RELEASE' --probe"   # real tracks, launches nothing
ssh mac "cd ~/walter-tv && python3 stremio.py $A --match 'RELEASE'"           # launch (wakes the TV)
ssh mac "cd ~/walter-tv && python3 stremio.py $A --state"                     # verify
```

## Steps

1. **Identify the work.** An episode described by its plot → find season/episode yourself (knowledge or one web
   search), then `--s/--e`. Homonyms/remakes → `--year`. Known non-English original → `--original-lang CODE`.
2. **`--list`** (~3.5 s): top 10 eligible sources. The script already rejected what the dongle cannot play
   (AV1, HDR/Dolby Vision, 3D, Remux, CAM/TS, average bitrate > 12 Mb/s, > 8 GB without known bitrate, 4K
   without HEVC + known bitrate + direct link, P2P under 10 seeds) and VOSTFR for a VF request. Take the top line
   unless the language rules below say otherwise.
3. **Name the release with `--match`** (distinctive part of its label: group tag + episode). Every call fetches
   a fresh ranking, so `--pick N` may point to another release next time. Probe and launch print the label they
   used: check it.
4. **`--probe`** (~2 s on a cached source) prints the real audio tracks and one verdict line:

   | Verdict | Do |
   |---|---|
   | `VF OK` · `… déjà retenu le français` · `… conforme à la langue du profil` | launch |
   | `… Basculer` · `… NON GARANTI` · `… INCERTAIN` | launch, then check and if needed switch the audio in the player (below) |
   | `VF ABSENTE` · `VF NON PROUVÉE` | probe the next candidate |
   | `source pair-à-pair … non sondables` | prefer a probed line; else report audio as unverified |

   VO: the profile prefers English (`eng`). If the original language is not English and the file has an English
   dub, the player is expected to start in English: switch to the original track. Never report a dub as VO.
5. **Launch** with the same `--match`. TV off → on HDMI2 automatically. First launch after the app was stopped:
   the script opens Stremio's home first (~15 s) so the subtitle server runs.
6. **Verify** (`--state`, then a screenshot):
   - `lecteur : en lecture, position ≈ m:ss, « title »`: the title must be the one you launched (the player line
     shows whatever is playing). Run it twice ~10 s apart: the position must move.
   - `piste audio retenue … fr` = Stremio's kept track for this title (VF evidence for a MULTi file).
   - English subtitles and timecode: `adb -s 192.168.1.37:5555 shell input keyevent KEYCODE_DPAD_DOWN` shows the
     control bar without pausing, then `adb … exec-out screencap -p > shot.png` and read it. Subtitles visible in
     English = verified. The audio language cannot be heard by an agent: report it from the evidence above.
7. **Fails to play** → next eligible release (lower bitrate / cached first, then lower resolution), same
   language; at most three attempts, then report the concrete blocker.

## Language rules (VF chosen on the release title, before launch: Monsieur's rule)

| Title tag | Audio | For a VF request |
|---|---|---|
| `TRUEFRENCH`, `VFF`, `VFQ`, `VF2`, `FRENCH` without MULTi | French only | **first choice**, nothing to switch (script ranks it ahead at equal quality) |
| `MULTi`, `MULTi.VFF`, `MULTi.VFi`, `MULTi.VF2`, `DUAL` | French + original | second choice; profile prefers English → may start in English unless French is kept for the title |
| `VOSTFR`, `SUBFRENCH` | original audio, French subtitles | **not VF**: rejected by the script |
| only the addon's 🇫🇷 flag | unknown | `--probe` before choosing |

For an explicit VF request keep English subtitles unless Monsieur says otherwise.

## Switching the audio track in the player (only when the probe says so)

Stremio keeps the chosen track per title (`--state` shows it) and reuses it, so this is needed once per
film/series. **Not yet verified end to end**; screenshots after every key:
- `KEYCODE_DPAD_DOWN` → control bar, focus on Play/Pause. Observed order: Play/Pause, Next episode, Rewind,
  Subtitles (CC), **Audio**, Speed, Fullscreen, PiP, Episodes.
- Move with `KEYCODE_DPAD_RIGHT`, check the focus halo on the screenshot, then `KEYCODE_DPAD_CENTER`, pick the
  French (or original) entry, `KEYCODE_BACK`. Once done for real, record here the exact number of RIGHT presses.
- CENTER on Play/Pause **pauses** (it happened): `--state` shows `en pause` → focus Play/Pause, CENTER again.

## What worked (2026-10-26)

- Deep-link launch of a cached HEVC 1080p `MULTi.VFi` episode (`--match TARDiS`): plays, `fr` kept for the
  title, English subtitles seen on screen.
- `--probe` on that file: audio #1 `fre` "FR VFi", #2 `eng` "ENG VO". On a `FRENCH DVDRiP`: one untagged track.
- `am force-stop com.stremio.one` then a launch: playback restarted from the beginning (observed once).

## What did NOT work / wasted time: do not repeat

- **Reading `position=` from `dumpsys media_session` raw**: it is a snapshot from `updated`, not refreshed while
  playing (raw 8:37 while the screen showed 17:59). `--state` now computes the real position.
- Stremio **resumes** a title where it was last left: a "launch" may start mid-episode. Say so, or force-stop first
  if Monsieur wants it from the start.
- An uncached (`TB⬇️`) XviD release with unknown resolution never opened the player; Stremio stayed on the
  detail page of the **next** episode. Check the episode in `--state` before concluding.
- Random DPAD presses in the player to find the audio menu (paused the film); `uiautomator dump` (empty in the
  player); grepping logcat for the audio language (nothing useful).
- Hand-written ffprobe/state scripts, Cinemeta queries by hand (a mistyped IMDb id cost 70 s), reading the script.
- On the Mac (zsh) a command stored in a variable (`A="adb … keyevent"; $A KEY`) fails: zsh does not split words.
- Never print or paste addon URLs or stream URLs: they embed Monsieur's TorBox/Real-Debrid keys. The script
  masks them; raw `core.xml` dumps must not be written to disk.

## When something else breaks

Subtitles missing (server down), dongle unreachable, sleep, app crashes → skill `tv-dongle-maintenance`.
TV power only → skill `tv-power`. Script options and internals → hub skill `android-tv-stremio-dongle`.

## Choisir la VF avant lancement et vérifier la lecture

- Choisir la langue dans l’intitulé de la release avant de lancer : Monsieur l’a explicitement demandé. Préférer une release indiquant FRENCH ou VF ; MULTi seul ne garantit pas le français. MULTi.VFi indique une piste française disponible, sans prouver qu’elle sera sélectionnée.
- Sur le Mac, utiliser `/usr/local/bin/adb` ou exporter `PATH=/usr/local/bin:$PATH` : `adb` était absent du PATH de la session SSH malgré son installation.
- Lister les candidats depuis le Mac : `ssh mac 'export PATH=/usr/local/bin:$PATH; cd ~/walter-tv && python3 stremio.py "south park" --s 12 --e 6 --lang fr --list'`. Adapter titre, saison et épisode. Lire les intitulés complets avant tout lancement.
- Ne pas mémoriser un numéro de candidat : il dépend de la liste courante. Relister immédiatement avant `--pick N` et vérifier que le numéro désigne toujours la release voulue. Si l’interface existante permet une sélection par intitulé, exiger une correspondance unique.
- Si nécessaire, sonder le média avant lancement avec ffprobe pour connaître les pistes, leurs langues et dispositions. Garder les URL signées privées et ne publier que les métadonnées utiles. Une piste unique sans étiquette de langue ne prouve pas à elle seule la VF.
- Après lancement, contrôler `ssh mac 'export PATH=/usr/local/bin:$PATH; adb -s 192.168.1.37:5555 shell dumpsys media_session'`. Vérifier la session `com.stremio.one`, les métadonnées du bon épisode et `PlaybackState` : `state=3` signifie lecture, `state=2` pause. Comparer deux positions espacées de quelques secondes pour confirmer la progression.
- Si l’état reste ambigu, capturer l’écran : `ssh mac 'export PATH=/usr/local/bin:$PATH; adb -s 192.168.1.37:5555 exec-out screencap -p > /tmp/stremio-check.png'`, puis récupérer et inspecter l’image. Une activité Stremio au premier plan ou un retour ADB OK ne prouve pas que la vidéo joue.
- Éviter les séquences de touches à l’aveugle pour chercher la VF après lancement. Dans cette session, la navigation a laissé le lecteur en pause et `uiautomator dump` n’a fourni aucun texte exploitable. Inspecter le focus avant toute activation nécessaire.
- Ne pas présenter comme réparation validée les essais de deep link ou de force-stop : cette session n’a pas établi qu’ils résolvaient l’échec de lancement.
