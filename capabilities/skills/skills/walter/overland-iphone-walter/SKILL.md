---
name: overland-iphone-walter
description: Configurer ou diagnostiquer Overland sur l’iPhone de Monsieur pour transmettre sa position à Walter Memory.
---

# Overland iPhone → Walter Memory

Lire d’abord `docs/OVERLAND.md` sous la racine retournée par `walter path memory` : procédure, limites et retour arrière à jour. Utiliser memory_context et vérifier l’état réel avant de conclure.

Le récepteur est `walter_memory.overland`, unité `walter-memory-overland`, lié à loopback :3010 derrière la route Cloudflare existante. URL iPhone : `https://loc.walter-ai.cloud/overland` ; Device ID `iphone`. Clé dédiée dans `@instance/bootstrap/overland.env` (0600), résoudre avec `walter instance path`. Ne jamais afficher la valeur ni l’inclure dans une URL, capture, prompt, journal ou argument. Transfert direct par stdin vers `ssh mac /usr/bin/pbcopy`, sans valeur dans les arguments ; Monsieur colle le champ Access Token sur iPhone via Continuité. Si indisponible, laisser Monsieur manipuler localement la valeur, pas le modèle.

Installer l’app officielle Overland GPS Tracker d’Aaron Parecki (App Store id1292426766), ouvrir, renseigner URL/device/token ; Tracking Enabled, localisation Toujours et Précise, autorisation Mouvement, Send Interval initial 1 minute, Send Now. Un iPhone détecté en USB ne prouve pas l’installation ; le Mac Intel vérifié le 28/10 n’avait ni Xcode ni Configurator ni outil d’installation iOS. Ne pas présenter l’installation comme accomplie sans preuve.

Tests du module : `walter-python -m pytest -q tests/test_overland.py` depuis Memory. Récepteur public limité à POST /overland + GET /health ; token distinct du gateway général. `result:ok` seulement après transaction validée. Raw canonical source overland, events location.sample/location.telemetry, local_only ; les refus cloud-safe doivent être respectés. Pas de coordonnées dans les diagnostics au modèle. Le profil serveur adapte intervalle selon mouvement/batterie sur un point récent ; iOS ne garantit pas l’intervalle.

Pour déclarer fonctionnel : vérifier un vrai événement location.sample après Send Now, timestamp récent, précision exploitable, file d’attente iPhone vidée ; refaire écran verrouillé en déplacement. Compter les événements et afficher seulement dates/fraîcheur pour les diagnostics cloud. Les probes synthétiques doivent être annulées par rollback, jamais conservées comme observations. La santé HTTPS seule ou un POST vide ne prouve pas la réception GPS. Le 28/10, HTTPS/auth/transaction/dédup/privacy vérifiés, réception téléphone encore en attente au moment de la rédaction.

Après changement mémoire, memory-autopilot puis contrôler son résumé. Avertissement beeper_media préexistant indépendant. Sauvegarder avant modification ; utiliser le module existant, ne pas relancer l’ancien walter-location archivé.
