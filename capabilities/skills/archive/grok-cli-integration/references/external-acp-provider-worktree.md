# Provider ACP externe dans un dépôt sale

## Quand l’utiliser
Quand l’ajout d’un provider CLI/ACP touche Hermes alors que le dépôt actif contient des modifications non liées.

## Procédure
1. Inspecter l’état Git sans modifier ni nettoyer le dépôt actif.
2. Créer un worktree depuis le HEAD courant : `git worktree add -b feature/<provider>-cli /tmp/hermes-<provider>-cli HEAD`.
3. Effectuer l’implémentation, les tests et le commit uniquement dans ce worktree.
4. Généraliser le transport `external_process` existant au lieu de copier un client par fournisseur : profil provider, registre auth, résolution runtime, client auxiliaire et décision de streaming doivent reconnaître le nouveau provider.
5. Définir séparément commande, arguments, marqueur `acp://...` et variables d’override propres au provider. Ne jamais réutiliser les variables Copilot pour un autre CLI.
6. Tester au minimum : présence dans le catalogue/picker, résolution exacte de commande+arguments, création du client ACP, route non-streaming et absence de régression Copilot.
7. Faire un smoke test réel du processus ACP quand l’auth locale est disponible.
8. Produire un commit autonome. Appliquer ensuite ce commit au dépôt actif seulement si les fichiers modifiés ne chevauchent pas les changements locaux ; sinon conserver le SHA et intégrer après nettoyage ou résolution explicite.

## Garde-fous
- Ne jamais abandonner uniquement parce que le dépôt principal est sale : isoler d’abord.
- Ne jamais écraser, stash, reset ou nettoyer les changements de Monsieur sans instruction explicite.
- Un échec d’authentification d’un agent de codage est un signal de bascule vers une autre voie d’exécution, pas une raison d’arrêter le chantier.
- Ne pas annoncer la disponibilité du provider avant tests ciblés et smoke test, ou avant d’avoir signalé clairement pourquoi le smoke test réel est bloqué.
