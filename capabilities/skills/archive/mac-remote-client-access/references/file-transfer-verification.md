# File transfer vers un Mac déjà configuré

## Quand l'utiliser

Pour déposer une archive ou un artifact sur le Bureau d'un Mac déjà joignable depuis W.Alter, sans passer par une procédure d'installation d'accès distant.

## Procédure validée

1. Créer l'archive côté W.Alter avec `zipfile` ou `zip`, en conservant un dossier racine stable. Compter les fichiers et calculer le SHA-256 local.
2. Vérifier l'état Tailscale et sélectionner le peer `OS=macOS` actuellement `Online`. Utiliser l'IP/hostname tailnet direct ; ne pas reprendre automatiquement un alias SSH pointant vers `localhost` ou un tunnel local.
3. Lire la configuration SSH existante pour récupérer l'utilisateur et la clé autorisée, sans afficher ni copier de clé privée.
4. Tester la cible avec SSH : `uname -s`, `$HOME`, et l'existence de `$HOME/Desktop`.
5. Vérifier si le fichier cible existe déjà avant transfert. L'écrasement n'est acceptable que si la demande utilisateur le couvre ; sinon choisir un nouveau nom ou conserver l'archive identique.
6. Transférer avec `scp` vers `$HOME/Desktop/<archive>.zip`.
7. Vérifier sur le Mac : `shasum -a 256`, taille, et `unzip -tq`. Comparer le hash distant au hash local ; ne jamais déclarer le transfert réussi sur le seul code retour de `scp`.

## Sécurité et périmètre

- Ne jamais archiver un `.env`, un vault exporté, une clé privée ou un token pour satisfaire une demande de packaging d'artifact. Vérifier que le dossier source ne contient pas de secret-bearing environment file.
- L'archive peut contenir les médias et les artifacts privés du job si Monsieur demande explicitement « tout le job ».
- Ne pas saisir de mot de passe dans une commande ou un outil.
- Le transfert est une opération de fichier ; il ne nécessite pas de piloter Finder ou le Bureau par GUI.
- Si le front door `computer_use(goal=...)` n'est pas disponible, utiliser cette route SSH/Tailscale directe seulement après découverte d'un peer Mac en ligne et vérification SSH réelle. Capturer la solution validée, pas l'échec transitoire du backend GUI.

## Preuve minimale à conserver dans le compte rendu

- chemin distant exact ;
- nombre de fichiers et taille de l'archive ;
- SHA-256 local et distant identiques ;
- résultat `unzip -tq` ou équivalent ;
- absence de génération ou modification non demandée du contenu de l'archive.
