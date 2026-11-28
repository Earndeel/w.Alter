---
name: html5-game-clones
description: Use when Monsieur wants a playable clone of a casual game.
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [game, canvas, html5, mac-delivery]
    related_skills: [walter-computer-use, mac-brave-walter]
---

# HTML5 Game Clones

## When
Monsieur asks for a clone/remake of a classic or casual game (Doodle Jump, Snake, Breakout, Flappy Bird…) to play in his browser. Validated end-to-end 2026-08-21 with a Doodle Jump clone — see `templates/doodle-jump.html`.

## Build pattern (single file, zero dependencies)
1. One `index.html`, all CSS+JS inline, no external assets — the server serves exactly one file.
2. Canvas at a fixed logical resolution (Doodle Jump: 420×640); scale to window via CSS, size the backing store with devicePixelRatio, and `ctx.setTransform(cw/W, 0, 0, ch/H, 0, 0)` every frame so game code stays in logical coords.
3. Fixed timestep loop: accumulator, update at 60 Hz (max 5 catch-up steps per frame), draw every rAF. Physics tuned per-frame at 640 px world height: GRAV≈0.36, JUMP_V≈-11.7.
4. Explicit states (menu/playing/paused/gameover) + ~600 ms input lockout after gameover so a held key can't instantly restart.
5. Unified input: keyboard (arrows/WASD, Space), mouse (click = shoot toward cursor), touch (drag = steer, tap = shoot) — all converted to logical coords via getBoundingClientRect.
6. Audio generated with WebAudio (oscillator sweeps + noise bursts), no files; resume the AudioContext on first user gesture; mute toggle (M).
7. Best score in localStorage.
8. Fidelity checklist before coding: list the real game's mechanics (platform types + behaviors, power-ups, enemies + how they're killed, hazards, scoring, screen wrap) and implement each. « Clone parfait » = mechanics, not just palette.

## Delivery: serve on VPS, open on the Mac (validated)
1. `cd <dir> && python3 -m http.server 8777 --bind 0.0.0.0` as a background process.
2. `ssh lucasjouvencon@100.127.150.1 'open "http://100.91.35.121:8777/index.html"'` — opens in the Mac's default browser. No CDP/anti-detect instance needed for a plain game page (that's mac-brave-walter territory).
3. Verify SERVER-SIDE: tail the http.server log — a `GET /index.html` from `100.127.150.1` is the proof of a real browser load. `open` exits 0 instantly and proves nothing.
4. Before delivery, extract the `<script>` body to a temp file and run `node --check` on it to catch syntax errors.

## Pitfalls
- First browser request can land ~80 s after `open` (browser launch + page load). Don't conclude failure early; poll the log.
- favicon.ico 404s in the log are normal noise, not an error.
- `ss -tn` established-connection checks are unreliable (keep-alive timing); request logs are the truth.
- The computer_use Operator backend may be unavailable on this host; the SSH `open` route above is the validated fallback for "put this URL on Monsieur's screen" and needs no GUI driver.

## Template
- `templates/doodle-jump.html` — complete validated Doodle Jump clone (normal/moving/breakable platforms, springs, jetpack, monsters, black holes, aimed shots, wrap-around, particles, generated SFX). Copy and re-skin for other clones; reuse its loop/input/audio/scaling scaffolding.
