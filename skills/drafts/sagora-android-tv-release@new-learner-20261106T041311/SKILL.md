---
name: sagora-android-tv-release
description: Use when publishing a Sagora Android build and installing or verifying it on Monsieur's TV through the Mac bridge.
---

## Publish a completed build

Work from `/apps/aiostreams`. Read its `README.md` and the release scripts before acting; verify current paths and release requirements. Back up files before changing them.

Wait for the GitHub Actions build to succeed before publishing:

```sh
gh run watch <RUN_ID> -R Earndeel/sagora --exit-status --interval 30
sh /apps/aiostreams/production/android-app/publish.sh <RUN_ID>
```

For long builds, use the runtime's background execution facility and read its completed output before continuing.

Inspect `/apps/aiostreams/production/front/app/android/update.json` and confirm that publication succeeded. Copy the TV artifact to the Mac:

```sh
scp /apps/aiostreams/production/front/app/android/sagora-android-armeabi-v7a.apk mac:walter-tv/apk/sagora-android-armeabi-v7a.apk
```

## Check whether the TV is available

Use the existing Mac bridge scripts in `~/walter-tv`; inspect their usage before changing their invocation. Check power state and the resumed activity:

```sh
timeout 150 ssh mac "cd ~/walter-tv && sh tvcheck.sh 'dumpsys power | grep -m1 mWakefulness; dumpsys activity activities | grep -m1 mResumedActivity'"
```

Capture the screen through `tvcheck.sh` and retrieve it through `tvpull.sh`:

```sh
timeout 150 ssh mac "cd ~/walter-tv && sh tvcheck.sh 'screencap -p /sdcard/sagora-before.png' && sh tvpull.sh /sdcard/sagora-before.png /tmp/sagora-before.png"
scp mac:/tmp/sagora-before.png /tmp/sagora-before.png
```

Inspect the fresh image. Avoid interrupting someone watching a film; postpone installation if the TV is in use or its state is uncertain.

## Install and verify on the device

Once the TV is available:

```sh
timeout 400 ssh mac 'cd ~/walter-tv && sh tvinstall.sh ~/walter-tv/apk/sagora-android-armeabi-v7a.apk'
timeout 150 ssh mac "cd ~/walter-tv && sh tvcheck.sh 'dumpsys package cloud.walter.sagora | grep -m1 versionName; am start -n cloud.walter.sagora/io.github.viren070.aiostreams.MainActivity'"
```

Confirm the installed version matches the intended release. Exercise the changed feature with remote-control input through `tvcheck.sh`, for example `input keyevent KEYCODE_DPAD_DOWN` and `input keyevent KEYCODE_DPAD_RIGHT`. Capture and retrieve a new screenshot after navigation; inspect the actual TV rendering before reporting success.

## Avoid stale evidence

The TV bridge can be slow. Wait for capture commands to finish successfully before opening local screenshots. Use a fresh capture filename for each check and confirm that `scp` succeeded. A local file left by an earlier command can show an old screen while the new capture is still running.

A successful GitHub build or web-browser check does not establish that the intended APK is installed or that the TV interaction works. Verify both the package version and the changed behavior on the device.
