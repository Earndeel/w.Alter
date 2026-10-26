#!/bin/sh
# Remet le dongle D6 dans l'état d'avant les changements du 2026-10-26.
# Usage : sh restore.sh [IP]   (sinon DONGLE_HOST ou ~/.config/stremio-remote/host), depuis ce dossier.
IP="${1:-${DONGLE_HOST:-$(cat ~/.config/stremio-remote/host 2>/dev/null)}}"
[ -n "$IP" ] || { echo "usage: sh restore.sh <IP du dongle>"; exit 1; }
DEV="$IP:5555"
cd "$(dirname "$0")"

adb connect "$DEV" >/dev/null

# Adups FOTA, retiré pour l'utilisateur 0 (le fichier est resté dans /product).
printf 'com.adups.fota -> '
adb -s "$DEV" shell cmd package install-existing com.adups.fota

# Les applis désactivées : les 3 autres applis système à risque, puis la liste debloat.txt.
for p in com.adups.fota com.ald.appstore com.oranth.memoryclean com.softwinner.update \
         $(grep -vE '^[[:space:]]*(#|$)' debloat.txt); do
  printf '%s -> ' "$p"
  adb -s "$DEV" shell pm enable "$p"
done

# L'écran d'accueil Google TV redevient l'accueil par défaut.
adb -s "$DEV" shell pm enable com.google.android.tvlauncher
adb -s "$DEV" shell cmd package set-home-activity com.google.android.tvlauncher/.MainActivity

# Animations : valeurs d'origine (1.0, 1.0 et non défini).
adb -s "$DEV" shell settings put global window_animation_scale 1.0
adb -s "$DEV" shell settings put global transition_animation_scale 1.0
adb -s "$DEV" shell settings delete global animator_duration_scale

# HDMI-CEC : la télé ne s'éteint plus quand le dongle se met en veille (valeur d'origine 0).
adb -s "$DEV" shell settings put global hdmi_control_auto_device_off_enabled 0

# Le dongle peut de nouveau passer en veille profonde (verrou posé par stremio-remote/stremio.py).
adb -s "$DEV" shell su -c "'echo stremio_remote > /sys/power/wake_unlock'" 2>/dev/null
adb -s "$DEV" shell rm -f /data/local/tmp/cecsend

# Retire le blocage réseau d'Adups (uid 10064), s'il est encore là (il disparaît au redémarrage).
adb -s "$DEV" shell su -c "'iptables -D OUTPUT -m owner --uid-owner 10064 -j REJECT; ip6tables -D OUTPUT -m owner --uid-owner 10064 -j REJECT'" 2>/dev/null

echo "Fait. Le launcher léger (com.gathin.tvhome) reste installé : adb -s $DEV uninstall com.gathin.tvhome pour l'enlever."
