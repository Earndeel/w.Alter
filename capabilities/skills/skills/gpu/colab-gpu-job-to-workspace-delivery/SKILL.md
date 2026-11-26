---
name: colab-gpu-job-to-workspace-delivery
description: "Use when Monsieur wants a Colab GPU job (inference, ComfyUI/GGUF workflow, compute-unit check) whose inputs, cache, outputs or report go through his Google account: Drive transfer/storage, Gmail report or confirmation, Sheets log, or Calendar follow-up."
type: workflow
requires: [colab-external-gpu, google-workspace]
---

# Job GPU Colab → livraison Google Workspace

Ce workflow ordonne deux skills. Il ne remplace ni leurs règles ni leurs commandes. À chaque étape, charger le sous-skill avec `skill_read` et appliquer ses garde-fous. En cas de conflit, le sous-skill fait foi.

## Quand l'appliquer

- Monsieur demande un calcul GPU sur Colab dont le résultat doit atterrir dans son compte Google : fichiers sur Drive, résumé par email, ligne dans un Sheet ou rappel Calendar.
- Un cache, une archive de dépendances ou des entrées doivent transiter par l'accès Drive déjà autorisé de l'agent, sans montage.
- Monsieur veut vérifier son plan, ses compute units ou une allocation, puis recevoir ou classer la synthèse.

Ne pas l'appliquer dans ces cas :
- question de faisabilité pure : n'utiliser que `colab-external-gpu`, sans rien lancer ;
- simple tâche email ou Drive sans GPU : n'utiliser que `google-workspace`.

## Étape 0 : cadrer (aucune allocation)

1. Reformuler l'objectif en quatre points :
   - quel résultat utile ;
   - quels livrables ;
   - où les livrer (dossier Drive, destinataire, Sheet) ;
   - le niveau de consommation acceptable.
2. Vérifier que l'authentification Google de l'agent est valide, en chargeant `google-workspace` avec `skill_read` pour la procédure de contrôle.
   - Si elle n'est pas valide, régler l'auth **avant** toute allocation GPU.
   - Ne jamais déboguer un login pendant qu'un GPU est alloué.

## Étape 1 : préparer, exécuter et libérer le calcul Colab

Charger `colab-external-gpu` avec `skill_read`, ainsi que la référence qu'il désigne pour le cas concerné (sonde, notebook GGUF, calcul à la demande sans montage, contrôle MCP).

- Suivre ses règles de préparation complète et de verrou avant allocation. Suivre aussi ses règles de choix d'accélérateur, de mesure réelle et de suppression du runtime.
- Si des entrées ou une archive doivent être déposées sur Drive avant l'allocation :
  - effectuer ce dépôt via `google-workspace` (le charger avec `skill_read`), verrou toujours fermé ;
  - revenir à l'étape 1 une fois les hashes confirmés.

**Ce que l'étape 1 transmet à l'étape 2** (consigner explicitement) :
- le statut réellement vérifié : fonctionnel, non validé ou bloqué, avec la raison ;
- le GPU effectivement attribué, tel que mesuré, et non le libellé affiché ;
- les durées et la consommation mesurées, ou la mention « non mesuré » ;
- la liste des artefacts. Pour chacun : emplacement (ID ou chemin Drive), taille, SHA256, paramètres et versions épinglées ;
- la preuve que le runtime de test a été supprimé ou libéré ;
- les éléments à **ne pas** livrer : secrets, tokens, données sensibles.

## Contrôle entre l'étape 1 et l'étape 2

- **Runtime :** aucun runtime ne doit rester alloué. Sinon, revenir à l'étape 1 pour le libérer avant toute livraison.
- **Artefacts :** chaque artefact annoncé doit exister avec son hash.
  - Un ancien fichier, un marqueur dans le code source ou une confirmation de chat ne valent pas preuve.
  - Si un artefact manque, le statut devient « non validé » ou « bloqué ».
- **Affirmations :** la synthèse ne doit contenir aucune affirmation au-delà de ce qui a été mesuré. Cela vaut pour la VRAM, les heures de calcul, le statut « gratuit » ou un workflow déclaré fonctionnel.
- **Statut bloqué :** livrer seulement un rapport d'échec honnête, sans artefact de repli.

## Étape 2 : récupérer, classer et notifier via Google Workspace

Charger `google-workspace` avec `skill_read`, ainsi que ses références Drive (upload, corbeille), Gmail ou Sheets selon le besoin.

1. **Récupérer** les artefacts depuis Drive sur la VM si nécessaire, puis recomparer leurs SHA256 avec la liste de l'étape 1.
2. **Classer** les livrables dans le dossier Drive convenu avec Monsieur :
   - utiliser la voie indiquée par le sous-skill pour l'upload et le déplacement ;
   - ne déposer aucun secret ni refresh token.
3. **Consigner** dans un Sheet de suivi, si Monsieur en a un ou en demande un : date, GPU réel, durée et consommation mesurées, statut, liens Drive, hashes.
4. **Notifier** :
   - préparer le résumé (entrées → modèles → étapes → sorties, statut vérifié, chiffres mesurés, liens) ;
   - le montrer à Monsieur avant tout envoi à un tiers ;
   - un envoi à Monsieur lui-même se fait seulement s'il l'a demandé.
5. **Nettoyer**, seulement après récupération vérifiée :
   - mettre à la corbeille les fichiers temporaires de transfert sur Drive, selon la procédure du sous-skill ;
   - conserver le cache persistant voulu (archive de dépendances, modèles) sauf instruction contraire.

## Contrôle final

- Les hashes des fichiers livrés correspondent à ceux de l'étape 1.
- Les liens Drive s'ouvrent avec le partage voulu, sans partage public par défaut.
- L'email ou le Sheet reflète exactement le statut et les mesures. Toute estimation est marquée comme telle.
- Aucun runtime Colab actif ne subsiste, et aucun secret ne figure dans les livrables.
- Signaler à Monsieur toute étape sautée ou restée « non validée ».
