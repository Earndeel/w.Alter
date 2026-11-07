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

## Vérifier une interface servie par le web sans interrompre la TV

- Pour les versions Android qui chargent l’interface du serveur (constaté avec `0.13.0-sagora.5`), distinguer livraison web et livraison APK : une modification du lecteur web arrive aussi sur la TV au redémarrage de l’application. Vérifier le lecteur TV après un déploiement web qui touche ses commandes.
- Avant CHAQUE action susceptible d’interrompre la TV (installation, lancement, redémarrage, navigation ou touches), contrôler à nouveau la lecture : `timeout 90 ssh mac 'cd ~/walter-tv && sh tvcheck.sh "dumpsys media_session | grep -E \"state=PlaybackState|package=\" | head -6; dumpsys window | grep -m1 mCurrentFocus"'`. Un contrôle effectué plus tôt dans la session ne suffit pas. Si une lecture est active ou si l’état est ambigu, différer les actions perturbatrices jusqu’à un créneau confirmé.
- Si `adb exec-out screencap -p` échoue avec `error: closed`, passer par le script de reconnexion puis un fichier sur le dongle : `timeout 120 ssh mac 'cd ~/walter-tv && sh tvcheck.sh "screencap -p /sdcard/sagora-qa.png"; export PATH=/usr/local/bin:$PATH; adb -s 192.168.1.38:5555 pull /sdcard/sagora-qa.png shot-sagora-qa.png'`. Récupérer ensuite l’image avec `scp mac:walter-tv/shot-sagora-qa.png <dossier-session>/tv.png` et l’inspecter.
- Pour les commandes audio, vérifier séparément les pistes du fichier courant et les langues proposées par d’autres versions. Les contrôles sont dans `/apps/sagora/code/packages/web/src/components/player/options.tsx`, la sélection de versions dans `lib/playback/version-languages.ts` sous le même dossier `src`. Le navigateur et le lecteur Android n’exposent pas nécessairement les mêmes pistes : une correction destinée au web peut créer un second bouton sur TV.
- Vérifier sur TV qu’un seul menu Audio apparaît, que les pistes du fichier sont distinguées des entrées « Autre version », et que changer de version conserve la position de lecture. Une capture de l’accueil ne valide pas le lecteur ; annoncer explicitement si cette vérification reste à faire.
