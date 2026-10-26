# D6 KeepAlive — 2026-10-26

Paquet Android local : cloud.walter.tvkeepalive, version 1.0.
Android réel vérifié : API 29. Application ciblant API 25 pour ce firmware uniquement.
Pas de permission Internet, pas de root pour fonctionner, pas de changement de firmware.

Le service Android de premier plan tient un PARTIAL_WAKE_LOCK et un WifiLock haute performance.
BOOT_COMPLETED et MY_PACKAGE_REPLACED le démarrent; START_STICKY demande sa relance après mort du processus.
Il ne réveille pas l'écran. Une notification permanente explique son activité.
Une désinstallation ou un force-stop explicite arrête volontairement la protection.

Installation depuis un hôte du LAN avec ADB déjà autorisé :

    adb connect 192.168.1.37:5555
    adb -s 192.168.1.37:5555 install -r keepalive.apk
    adb -s 192.168.1.37:5555 shell dumpsys deviceidle whitelist +cloud.walter.tvkeepalive
    adb -s 192.168.1.37:5555 shell am start -n cloud.walter.tvkeepalive/.StartActivity

Vérification :

    adb -s 192.168.1.37:5555 shell dumpsys activity services cloud.walter.tvkeepalive
    adb -s 192.168.1.37:5555 shell dumpsys power
    adb -s 192.168.1.37:5555 shell dumpsys wifi

Attendus : isForeground=true; PARTIAL_WAKE_LOCK walter:tvkeepalive; WifiLock du même nom.
Un écran Asleep est normal si le verrou et ADB restent actifs.

Annulation ciblée (ne réinitialise aucun autre réglage) :

    adb -s 192.168.1.37:5555 shell dumpsys deviceidle whitelist -cloud.walter.tvkeepalive
    adb -s 192.168.1.37:5555 uninstall cloud.walter.tvkeepalive

L'ancien verrou noyau stremio_remote, s'il est posé par stremio.py, est indépendant.
Sa suppression volontaire nécessite root : echo stremio_remote > /sys/power/wake_unlock.
Ne pas le supprimer pour une simple mise à jour du service.

Tests réels :
- installation, service de premier plan, verrous CPU/Wi-Fi vérifiés;
- vrai redémarrage : boot_id changé, service automatiquement présent sans relance manuelle;
- arrêt du seul processus par kill -9 : nouveau PID et verrous rétablis après 12 secondes;
- écran endormi : ADB et les deux verrous présents après 20 secondes;
- écran rallumé à l'issue du test.

Non testé : coupure physique de l'alimentation, stabilité sur plusieurs heures/jours.
Un arrêt électrique/PMIC ne peut pas être annulé par ce service qui ne s'exécute plus.
Alimentation USB secteur indépendante si le port TV coupe ou fournit un courant insuffisant.
Ne pas désactiver les protections thermiques.

APK signé SHA-256 : 5581648b25f0d53632208951b48219ef1ed6d63a13963981ff164cda927d50cc
Clé de signature et état précédent : sauvegarde privée dongle-keepalive-20261026 sous le répertoire de sauvegardes Hermes.
La clé et son mot de passe sont exclus de cette archive.

Recompilation : Java 21; android.jar API 23 du paquet Ubuntu libandroid-23-java; AAPT ARM64 et bibliothèques Ubuntu;
D8 officiel R8 8.3.37, https://storage.googleapis.com/r8-releases/raw/8.3.37/r8.jar.
build.py attend ces outils sous toolchain/ et r8.jar dans son répertoire.
Paquets utilisés : aapt, android-libaapt, android-libandroidfw, android-libbase, android-liblog,
android-libutils, android-libziparchive, android-libcutils, android-libbacktrace, libandroid-23-java.
Ils ont été extraits avec dpkg-deb -x, sans installation système.
Réutiliser la clé privée sauvegardée pour une mise à jour conservant la signature.


Archive durable Raw Vault : dfb24fd5-3f35-47ec-bb34-46e80ad460b0 (vault_get pour récupérer APK signé, sources Java, manifeste et build.py).
Sauvegarde VM : /root/.hermes/backups/dongle-keepalive-20261026/ (before.txt, archive; clé privée séparée, jamais afficher).
Le test de redémarrage a changé boot_id, et le service était présent avant toute relance manuelle.
Le dernier motif de veille initial était hdmi; cela prouve une veille écran déclenchée par CEC lors de cette observation,
pas l'origine de toutes les extinctions rapportées. Aucune modification de CEC ni de thermique n'a été faite.
