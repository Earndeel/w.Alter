---
name: mac-computer-use-ssh
description: "Diagnostic et qualification d'une surface Mac synthétique via le transport SSH de Walter Computer ; respecter les gardes de cible, les autorisations et la confidentialité."
version: 4.0.0
author: walter
metadata:
  hermes:
    tags: [computer-use, mac, ssh, qualification]
---

# Walter Computer : transport Mac et qualification sûre

## Interface actuelle

Lire d'abord les skills `durable-computer-use-architecture`, `walter-computer-use` et `computer-use`. La façade canonique est `/opt/walter-computer`, exposée par `computer_use` aux harnesses. Le transport Mac réside dans `/root/walter-computer-use`; son paramétrage privé est `/root/.config/walter-device-node/remote-cua.json`. Vérifier la configuration active sans afficher ses secrets.

Le transport SSH n'est pas une autorisation d'agir. Conserver les permissions du harness, le contrôle de présence humaine et les gardes de cible du module. Utiliser une référence AX fraîche quand elle existe. Les références visuelles sont ciblées, éphémères, consommables une fois ; aucune coordonnée inventée ni répétition d'une action dont l'achèvement est inconnu. Une réservation de tâche sérialise les clients, elle n'accorde pas le consentement humain.

L'observation et le contrôle doivent rester limités à l'application explicitement autorisée. Aucune capture générale du bureau pour qualifier le transport. Les captures privées ne doivent pas partir au cloud. Le capteur visuel autonome passe par Walter LLM avec le poste configuré ; l'autorisation `VisionPermission` vient du code hôte de confiance, liée au PID et à la fenêtre exacte. `local_only` et l'absence d'autorisation cloud sont des refus.

## Qualification GUI synthétique depuis SSH

Une application Cocoa lancée dans la session SSH Background peut exister sans fenêtre visible. La présence d'un PID ou `NSWindow.isVisible` ne suffit pas. Vérifier le job launchd et la fenêtre effectivement exposée par l'inventaire Walter.

1. Créer un répertoire temporaire propre à l'essai et une petite application de test sans données personnelles. Prévoir une durée maximale et une action sans effet externe, par exemple un bouton qui écrit uniquement un fichier témoin dans ce répertoire.
2. Pour une application native compilée, utiliser le SDK macOS disponible sur la machine. Un petit programme Objective-C/Cocoa compilé avec `clang -fobjc-arc -fno-modules -isysroot <SDK> -framework Cocoa` a été validé ; les imports Swift/JXA ne constituent pas une solution de repli garantie.
3. Créer un plist temporaire à nom unique, `RunAtLoad=true`, `LimitLoadToSessionType=Aqua`, `ProgramArguments` limités au programme de test ; stdout/stderr dans son répertoire. Ne pas installer de service permanent pour ce test.
4. Obtenir l'UID du compte Mac et charger uniquement ce job avec `launchctl bootstrap gui/<uid> <plist>`. Vérifier son état avec `launchctl print gui/<uid>/<label>`. `launchctl submit` depuis SSH peut rester dans le domaine Background.
5. Pour une qualification explicitement autorisée à afficher sa propre fenêtre, l'application de test peut utiliser `NSWindowCollectionBehaviorMoveToActiveSpace`, `activateIgnoringOtherApps:YES` et `makeKeyAndOrderFront:`. Cela affiche la fenêtre de test sur l'espace courant ; ne pas appliquer cette recette aux applications personnelles. Définir explicitement l'apparence Aqua et un texte contrasté pour éviter un bouton blanc illisible sur fond blanc.
6. Réserver le périphérique via `lease_acquire` pour une durée bornée, puis sélectionner exclusivement le PID et l'identifiant de fenêtre du programme de test. Capturer cette cible avec `mode=ax`. Ne conserver aucune autre ligne d'inventaire ni aucun contenu personnel dans les preuves.
7. Pour un test vision, autoriser seulement les pixels de cette fenêtre synthétique au niveau de l'hôte ; utiliser le poste configuré, sans modèle codé en dur. Consommer immédiatement la `visual_ref` et faire une vérification ciblée. Une géométrie vide ou une confiance insuffisante doit empêcher le clic.
8. Vérifier séparément la postcondition du programme. Un résultat natif `effect=unverifiable` ne prouve pas l'effet. À l'inverse, ne pas perdre une postcondition indépendante confirmée à cause d'un libellé conservateur du pilote.
9. Dans un `finally`, supprimer le seul job de cet essai avec `launchctl bootout gui/<uid>/<label>`, fermer les transports/réservations, puis supprimer son répertoire temporaire exact. Vérifier les trois nettoyages.

Conserver uniquement les métadonnées de résultat, les erreurs expurgées, les versions et les hachages nécessaires. Une image de la fixture purement synthétique peut servir à diagnostiquer son rendu ; ne pas y mêler d'autres fenêtres.

## Diagnostiquer sans affaiblir les gardes

- Absence de fenêtre : distinguer domaine launchd, application masquée/espace de travail et permissions macOS. Ne pas essayer des clics globaux pour la faire apparaître.
- Capture noire ou vide : vérifier la cible exacte et les autorisations système du processus effectif. La taille compressée de l'image n'est pas un diagnostic fiable, et les permissions TCC ne se déduisent pas du parent SSH. Aucun contournement des permissions macOS.
- Cible visuellement illisible : inspecter uniquement le crop synthétique autorisé et corriger la fixture ; ne pas réduire le seuil de confiance.
- Action envoyée, effet inconnu : vérifier une postcondition ciblée avant toute nouvelle entrée. Aucune répétition aveugle.
- Réservation détenue par un autre client : retourner occupé ; attendre une nouvelle autorisation ou l'expiration normale, sans prendre possession de sa tâche.
- Les sessions de navigation authentifiées passent par Walter Browse et ses interfaces gérées. Ne jamais extraire les cookies Brave ni manipuler les applications personnelles pour qualifier Computer.

## Anciens templates

Les templates historiques `walter-screen-server*.py` et `com.walter.screen-server.plist` sont des archives, pas le pilote actif. Ne pas les installer ni ouvrir leur serveur HTTP comme solution de repli. Le template v5 contient notamment une erreur de syntaxe à la ligne 91 constatée le 2026-10-18 ; sa réécriture complète n'a pas été publiée, car elle republierait un ancien serveur de capture et contrôle non authentifié. Une éventuelle remise en service de ces archives exige un chantier de sécurisation explicite, pas une simple correction de syntaxe. Ne pas modifier les copies curator historiques.
