---
name: walter-shared-modules-operations
description: Vérifier et exploiter les modules Walter partagés entre Hermes, DSH, Codex et Claude Code, leurs ports et sauvegardes.
---

# Modules Walter et harnesses

Lire `/opt/walter-core/README.md`, le registre `/opt/walter-core/modules/registry.json` et les README du module concerné. Walter possède les capacités/données communes ; le harness possède la boucle et les contrôles d'autorisation. Ne jamais modifier le checkout upstream Hermes pour intégrer une capacité.

## Vérifier avant de changer

1. `walter check` valide présence et imports des noyaux déclarés ; `walter status` ajoute les états systemd. Ce ne sont pas des tests de parcours utilisateur.
2. `walter harness check hermes|dsh|codex|claude-code` lit les branchements actuels. Configuration présente et code déjà chargé sont différents.
3. Sauvegarder noyau, adaptateur et configuration avant modification. Conserver les modifications préexistantes étrangères au lot.
4. Les sources Computer, Secrets, Browse sont `/opt/walter-computer`, `/opt/walter-secrets`, `/opt/walter-browse`. Les plugins Hermes sont leurs ports ; ne pas y recréer une seconde implémentation.

## Intégrer un client

`walter harness attach <client> [--home CHEMIN]` affiche un aperçu. `--apply` installe uniquement la connexion MCP, avec sauvegarde atomique ; aucun changement implicite de modèle/compression/permissions. Hermes utilise ses ports natifs, sans MCP dupliqué. Reconnecter un client existant pour découvrir les nouveaux outils. Prouver une installation par handshake MCP frais et appels sûrs, jamais seulement par une entrée de configuration.

## Contrats sensibles

- Secrets MCP renvoie métadonnées et références ; `walter-secret exec` injecte localement sous les permissions du harness et supprime la sortie enfant. Ne jamais afficher, copier ou mettre en URL les valeurs. Le remplissage navigateur propre à Hermes reste un port.
- Computer MCP est stdio local, autorisations dans le fichier protégé `modules/computer-policy.json` et dans le host. Le modèle ne fournit pas ses grants. Un verrou par appareil protège chaque appel, pas un workflow complet. Pas de clic/capture du Mac pour un simple contrôle de santé. Vision autonome indisponible sans capteur configuré.
- Browse : même façade et état pour tous. Sessions bornées au répertoire de stockage. Ancien script de skill = lien de compatibilité.
- Mémoire MCP `recall/retain/reflect` utilise `walter_memory.agent_memory` par JSON stdin. Vérifier confidentialité/provenance actuelle, rétractions, purges et texte indexé périmé. Ne pas ajouter de repli direct vers le bank Hindsight historique. Hermes Hindsight et la voix restent distincts.
- DSH : désactiver `compaction-basic`, insérer le port `/opt/walter-context/ports/dsh/index.mjs`, vérifier le dump de composition. Le host conserve journal/transaction/replay. Checkpoint refuse dépassement des consignes utilisateur ou instructions system/developer intercalées. `context_recover` lit uniquement le journal de la session. Hermes reste sur `walter-compress` tant que son mode projection n'est pas qualifié.

## Validation et sauvegarde

Tests propres aux modules et ports : README de chaque dépôt. Contexte : pytest dans le venv Hermes et `node --test /opt/walter-context/tests/test_dsh.mjs`. Mémoire : venv `/opt/walter-memory/venv` (pas le venv Hermes, qui manque psycopg). Test PG opt-in `WALTER_TEST_PG=1` utilise des tables TEMP puis rollback.

`walter backup-paths` alimente le bundle : déclarer aussi configurations entre modules, liens `/usr/local/bin`, tmpfiles et dépendances hors `/opt`. PG et state.db principal sont séparés ; profils SQLite snapshotés dans le bundle. Vérifier le flux distant déchiffré avec `python -m walter_memory.backup_bundle verify - --check-current` sans extraire ni afficher les secrets. Ce contrôle ne prouve pas une restauration VM vierge.

Après changements mémoire : lancer `memory-autopilot` et lire son résumé. Recharger Hermes via `hermes gateway restart` gracieux ; vérifier le backend Desktop inactif avant son redémarrage. Ne pas arrêter le serveur MCP de la conversation active.
