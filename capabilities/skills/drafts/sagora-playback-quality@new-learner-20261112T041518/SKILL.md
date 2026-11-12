---
name: sagora-playback-quality
description: Use when Sagora starts playback in the wrong audio language or selects a poor-quality source despite a high advertised resolution.
---

## Locate the implementation and operational tooling

Work in `/apps/sagora`. Read `docs/ARCHITECTURE.md` and `docs/EXPLOITATION.md` before changing production.

Relevant paths:
- Backend and shared code: `/apps/sagora/code/packages/`
- Web app: `/apps/sagora/code/packages/web/`
- Playback selection: `src/lib/playback/play.ts`
- Other selection entry points: `src/lib/playback/fallback.ts`, `src/lib/playback/adaptive.ts`, `src/pages/player.tsx`, `src/components/player/next-episode.tsx`, `src/components/version-picker.tsx`
- Account playback preferences: `src/lib/user-config.ts`
- Player capabilities: `src/lib/playback/player-choice.ts`
- Backend sorting criteria: `packages/core/src/utils/constants.ts`
- Production configuration helper: `/apps/sagora/production/tools/famille_config.py`
- Existing Mac browser test: `/apps/sagora/production/tests/mac_brave_playback.py`

Inspect the existing test and helper before adapting them; do not assume their account or episode is appropriate.

## Back up before changing account configuration

Create a dated directory under `/user/Lucas/backups/changes/` with mode 700 and use `umask 077` for configuration exports. Retrieve credentials through `walter-secret` without printing them.

The production configuration API is `http://127.0.0.1:18090/api/v1`. Configuration GET responses include `userData` and `encryptedPassword`. Read the helper and route implementation before writing: **PUT `/api/v1/user` replaces the entire configuration**, not just supplied preferences. Save the original full configuration and preserve unrelated settings and addons.

The local Jellyfin-compatible endpoint used for playback investigation is `http://127.0.0.1:18085/jellyfin`.

## Diagnose the actual source, not the resolution label

1. Reproduce with the affected account, client type, and episode.
2. Inspect the server's ordered media sources and the source the browser actually starts. Record resolution, bitrate, size, codec, default audio language, and selected subtitles without logging authentication material.
3. Distinguish server ordering from client-side reordering. A source ranked first by the server may move after language or compatibility filtering.
4. Check the default audio track, not merely whether the file contains the requested language. In the tested browser playback path, the browser played the default track even when the desired language existed elsewhere in the file.
5. Gate language-based source reordering on the selected player's audio-switching capabilities. Do not apply browser limitations indiscriminately to native players that can switch tracks.
6. Check quality sorting after resolution. Release type, audio codec, or video codec preferences can promote a heavily compressed source over a substantially higher-bitrate source at the same resolution. Inspect available sorting keys before changing preferences:

```sh
cd /apps/sagora/code/packages/core/src
grep -n -A45 '^export const SORT_CRITERIA' utils/constants.ts
grep -n 'bitrate' utils/constants.ts
```

Prefer actual bitrate immediately after resolution when the requested objective is image quality, while retaining language and compatibility constraints. Do not claim that a 1080p label guarantees a good image.

## Keep selection consistent and validate changes

If changing shared selection logic, inspect initial playback, fallback, adaptive switching, next-episode playback, and the version picker. Ensure each relevant call receives the account's playback preferences.

```sh
cd /apps/sagora/code/packages/web
npx tsc --noEmit -p .
pnpm build
```

The session encountered 18 pre-existing TypeScript errors. Treat this as historical evidence, not an allowed permanent error count: compare diagnostics against the unchanged baseline and check for newly introduced errors. Avoid casually stashing unrelated work to obtain a baseline.

For deployment, consult `docs/EXPLOITATION.md`. The observed layout uses immutable copies in `/apps/sagora/production/web-builds/<UTC timestamp>/`, containing built `dist` assets plus `BUILD` and `BASE_COMMIT` metadata, and serves assets from `web-dist`. Preserve the previous build and follow the documented deployment/rollback procedure; a successful local build is not proof of deployment.

## Verify real playback on Monsieur's Mac

Use the existing Mac playback test as the starting point. For an isolated Brave probe, start a temporary profile and a loopback-forwarded CDP endpoint:

```sh
ssh mac 'P=$(mktemp -d /tmp/brave-probe.XXXX); nohup "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" --headless=new --remote-debugging-port=9333 --user-data-dir="$P" --mute-audio --no-first-run about:blank >/dev/null 2>&1 & sleep 4'
ssh -f -N -L 9333:127.0.0.1:9333 mac
```

Run the adapted Playwright probe through the public application URL, using the affected account with credentials retrieved privately. Verify all of:
- selected source identity and actual bitrate;
- default/playing audio language;
- playback advancing without an error;
- subtitle selection **and visible subtitle text during dialogue**;
- a screenshot of the resulting image.

An API-reported subtitle selection alone does not prove subtitles rendered. An empty subtitle overlay during silence does not prove failure. A screenshot alone does not establish a universal bitrate ceiling: state limits only for the tested episode, sources, and client.

## Clean up and document

Track probe and tunnel PIDs where possible and terminate only processes created for the test. Avoid unescaped `pkill -f` patterns embedded in the invoking shell command: one cleanup command in this session matched itself and exited with code 144 before documentation ran.

Confirm tunnel closure:

```sh
ss -ltn | grep ':9333'
```

Remove only the temporary browser profiles created for the probe. Document configuration changes, backup locations, deployed build, rollback reference, and observed playback evidence in `docs/EXPLOITATION.md`; then review the diff and commit intended changes only.
