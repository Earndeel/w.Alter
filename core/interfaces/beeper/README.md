# Beeper — canal natif du moteur

| | |
|---|---|
| **Rôle** | Relier le Beeper Server officiel autonome aux lectures de Walter et aux envois autorisés par Walter Engine. Transport REST/WS commun, pas de boucle d'agent ni de second historique. |
| **Propriétaire** | core ; `walter_beeper.py`. Memory possède l'ingestion, les événements et leurs points de reprise. L'application fournisseur est dans `/apps/beeper/server`. |
| **État** | Implémenté le 16/11/2026 ; preuves de déploiement et de qualification dans le rapport du changement de l'instance. |
| **Ne fait pas** | Réinitialiser une clé de récupération, connecter/déconnecter un bridge, supprimer un message, marquer lu, envoyer sans politique du moteur, réessayer automatiquement un envoi dont la réponse s'est perdue. |
| **Contrats** | `contracts/core.json`, `walter_beeper.BeeperClient`, MCP `beeper_read` / `beeper_send_message`, politique unique `security/policy.json`. |

## Configuration et accès

`walter instance config core beeper.toml` : URL locale (23374), identifiant d'autorisation Secrets,
identité stable du profil pour ses curseurs et fenêtre de réconciliation. Aucun jeton dans la configuration.
`BeeperClient(consumer="memory")` est en lecture ; l'accès au coffre passe par
`walter_secrets.grants.access` avec lecteur nommé. Le serveur et sa session native restent supervisés par
`beeper-server.service`, sans affichage, Wayland, D-Bus de session, Mac ni serveur MCP supplémentaire.

`beeper_read(operation="chats"|"messages"|"search"|"accounts"|"status", ...)` expose uniquement ces lectures.
Les identifiants complets de conversation sont conservés : les petits identifiants locaux et les curseurs opaques
ne se transportent pas entre profils. Le jeton d'API ne figure jamais dans un résultat d'outil, une URL ou un log.

`beeper_send_message(chat_id, text, reply_to="")` est enregistré uniquement dans le MCP stdio du moteur
(`dsh`/`engine`), si `[dsh.engine] policy="enforce"`. La classe `outgoing` de la politique existante impose
le contrôle de divulgation Memory ; portes API → demande, commande/enfant → refus. Le noyau garde ses propres
permissions. Les clients de développement et HTTP MCP ne reçoivent pas d'outil d'envoi.
Un timeout d'envoi signifie **résultat inconnu** : consulter l'historique avant toute décision de réessayer.
Le transport n'offre pas de garantie « exactement un envoi » que l'API fournisseur ne propose pas.

## Ingestion et reprise

`memory/connectors/beeper_watch.py` reçoit `/v1/ws`, s'abonne avec `subscriptions.set` et dépose les snapshots
dans la file **existante** `ingestion.jobs` (`beeper_events`). Le connecteur existant transforme les messages en
`core.events`, médias en jobs `beeper_media`, puis Raw Vault ; le bus existant déclenche la suite de Memory.
Les snapshots sont masqués avec le filtre de secrets existant avant la mise en file. Les identifiants API de
message sont locaux à l'installation. Le connecteur retrouve l'identifiant canonique déjà dans Memory par
conversation et `sortKey`, vérifiés par date, sens et expéditeur (deux formes d'identifiant du propriétaire sont
admises pour un message explicitement sortant). Pour un nouveau message, l'identifiant est `chatID|sort:<sortKey>`.
Cette projection et les alias locaux restent dans les checkpoints existants ; aucun second catalogue.
La clé d'idempotence reste `(beeper, source_id canonique, event_type)` ; une redélivrance après crash ne double pas l'historique.
Événements, jobs médias et curseur d'une page sont validés dans la même transaction.

Le protocole Beeper est **at-most-once**, sans replay ; `seq` repart à chaque connexion. Il ne constitue donc pas
un journal durable. Chaque reconnexion ou trou de séquence programme un rattrapage HTTP, et le service périodique
existant garde la réconciliation : nouveaux messages jusqu'au dernier ordre connu de Memory ; récupération
sur un jour, bornée au plus tôt à `cutover_at`. Aucun backfill des conversations anciennes lors de cette bascule.
Pour une conversation inconnue, seuls les messages postérieurs à cette date sont pris en charge.
Les anciens points Mac restent dans les mêmes documents de checkpoint, et le nouveau profil utilise
`cursor.endpoints.<checkpoint_scope>` ; aucun historique ni ancien curseur n'est effacé.
Le retrait d'une conversation ne provoque aucune purge de ses messages.

Les suppressions/modifications sur des messages antérieurs à la fenêtre de récupération, survenues pendant une
coupure et absentes des lectures HTTP, ne peuvent pas être garanties par ce protocole sans replay. Les événements déjà observés restent
durables ; une réconciliation historique explicite peut élargir la fenêtre. Ne pas présenter le WS seul comme
une garantie de livraison ou une sauvegarde des réseaux sources.

## Exploitation

Services : `beeper-server`, `walter-memory-beeper-watch`, `walter-memory-beeper.timer` (réconciliation/médias).
Ne pas utiliser `beeper targets start/enable` en parallèle : systemd reste le seul superviseur de l'instance.
Le CLI officiel sert aux diagnostics (`status`, `api get`, `chats`, `messages`, `watch --json`).
La release CLI 0.6.4 a un défaut de SDK sur `auth email start` (`client.app.login.start` absent) ; le déploiement
a utilisé les routes REST officielles `/v1/app/setup/{start,email,response}` et la vérification SAS entre deux
appareils du propriétaire. Aucun correctif local du code fournisseur, reset de récupération ou ajout de bridge.

Versions figées et empreintes dans `/apps/beeper/server/provenance.json`. Pour toute mise à jour : canal
production/stable explicitement vérifié, profil test isolé, API réellement testée. Incidents officiels
[#21](https://github.com/beeper/cli/issues/21) et [#31](https://github.com/beeper/cli/issues/31) : ne pas déduire
le fonctionnement de l'API de l'état de SQLite ; correctif annoncé en Server 4.3.121+, vérifié sur 4.3.308.

Tests : `tests/test_beeper.py` de core ; `tests/test_beeper_native.py` et `tests/test_beeper_gap.py` de Memory,
base jetable 5440 uniquement ; vecteurs de politique Python/JS et test du greffon réel. Aucun envoi réel aux contacts
du propriétaire ne fait partie de ces tests. Après une modification des services Memory : lancer Memory autopilot.
