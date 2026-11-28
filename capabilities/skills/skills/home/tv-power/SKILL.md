---
name: tv-power
description: "Use when Monsieur asks to turn the living-room TV (Hisense) on or off, or to check whether it is on. Two commands, ~10 s, verified by the TV's own CEC reply."
---

# Living-room TV: on / off / is it on?

Fast, isolated procedure. Scripts live in the hub skill `android-tv-stremio-dongle` (read it only if this fails).
Run from the Walter VM; the Mac (`ssh mac`) is on the home LAN with the dongle (192.168.1.37) and the TV (192.168.1.36).

```
D=$(walter path skills skills/media/android-tv-stremio-dongle)
ssh mac "mkdir -p ~/walter-tv" && scp -q "$D/scripts/stremio.py" mac:~/walter-tv/
ssh mac 'cd ~/walter-tv && python3 stremio.py --on'     # TV on, lands on HDMI2 (the dongle)
ssh mac 'cd ~/walter-tv && python3 stremio.py --off'    # TV off (works even from the VIDAA home screen)
```

**Verify with the TV's answer, never with "command sent"** (one CEC query, invisible on screen):

```
ssh mac '/usr/local/bin/adb -s 192.168.1.37:5555 shell "su -c \"/data/local/tmp/cecsend 0 8F\""; sleep 2;
         /usr/local/bin/adb -s 192.168.1.37:5555 shell dumpsys hdmi_control | grep "Report Power Status" | tail -1'
```

`[R] … <Report Power Status> 04:90:00` = TV **on** · `04:90:01` = **standby** · no new `[R]` line = no answer
(TV unpowered at the wall, or CEC asleep): say so, do not guess. Check the `[R]` timestamp is the one you just
caused. `cecsend` prints `statut=1 (?)`: normal (verified 2026-10-26).

## What works (verified with Monsieur watching, 2026-10-26)

| Action | Result |
|---|---|
| `--on`: wakes the dongle screen (`KEYCODE_WAKEUP`) → it sends CEC `<Image View On>` + `<Active Source>` | TV turns on **on HDMI2**, because the TV setting "Default startup page = Last accessed source" is set (Monsieur did it; required) |
| `--off`: CEC `<Standby>` addressed to the TV (`cecsend 0 36`), then `KEYCODE_SLEEP` on the dongle | TV turns off, even when it shows the VIDAA home. The dongle screen sleeps but stays reachable over ADB (KeepAlive service) |
| `cecsend 0 8F` (`<Give Device Power Status>`) | TV answers, readable in `dumpsys hdmi_control` |

## What does NOT work: do not retry

- **Switching the TV input to HDMI2 from VIDAA over CEC**: `<Active Source>`, `<Set Stream Path>`, UI keys
  (Input/Select/`69 02`), Home key (One Touch Play), repeated Active Source during boot. VIDAA ignores them all.
  Only the "last accessed source" setting gets HDMI2 at power-on.
- Broadcast `<Standby>` (what the dongle sends when it sleeps): obeyed only while the TV is already on HDMI2.
- Wake-on-LAN (dongle or TV), Hisense MQTT :36669 (needs the official app's client certificate; Monsieur has no
  Android phone), AirPlay pair-pin-start (only shows a PIN on VIDAA). Abandoned.

## Pitfalls

- `--on` does nothing if the dongle screen is already awake (it only wakes a sleeping screen). If the CEC query
  then says standby, the TV was turned off by its own remote while the dongle stayed awake: `--off` then `--on`
  is the expected fix but has **not been tested**; verify with the query afterwards.
- "Dongle unreachable" from the script → not a TV problem: see skill `tv-dongle-maintenance`.
- Never leave the TV on after a test Monsieur did not ask for.
