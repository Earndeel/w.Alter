# core/interfaces/telegram — porte Telegram du moteur

| | |
|---|---|
| **Rôle** | Le bot Telegram propre à Walter (lot E7) : recevoir et répondre, sur le moteur Walter, avec l'identité (Soul), la mémoire, le contexte, Router, les outils et les sous-agents du moteur ; interruption, erreurs, approbations, suivi de la tâche. |
| **Propriétaire** | walter-core (interfaces). |
| **État** | En service depuis le 10/11/2026 (`walter-telegram.service`), bot du grant `telegram-walter-bot` ; scénario `../../scenarios/v1/telegram_door.py`. Le bot historique tenu par Hermes reste à Hermes jusqu'à sa sortie (E6). |
| **Ne fait pas** | Aucune boucle, session, choix de modèle ni permission à lui : tout passe par l'Engine API (`../api`). Ne sert que les comptes Telegram du propriétaire (`owner_ids`), en conversation privée ; tout autre message est ignoré et journalisé. Pas encore de notes vocales (réponse explicite). |
| **Contrats** | Engine API v1 (`../../engine/contracts/engine-api.v1.json`) ; Bot API Telegram (long polling). |

## Fonctionnement

- Une conversation privée du propriétaire = une conversation du moteur `telegram/<compte>/chat-<id>` (persistante, y
  compris après redémarrage ; `/nouveau` passe à `chat-<id>-<n>`).
- Chaque message → `turn.submit` avec l'id du message Telegram comme clé d'idempotence : une mise à jour livrée deux
  fois (redémarrage, réseau) ne s'exécute qu'une fois. Les messages envoyés pendant un tour sont mis en file.
- Le flux d'événements de la session (SSE, reprise au dernier `seq` vu) pilote l'affichage : « écrit… », une ligne
  d'état discrète avec les outils au travail (supprimée à la fin), la réponse (Markdown → HTML Telegram, découpée à
  4 096 caractères), ou la fin d'un tour interrompu / en échec / au budget atteint, dite explicitement.
- Approbations : une demande `ask` du moteur (y compris d'un sous-agent) devient un message à deux boutons
  (« Autoriser une fois » / « Refuser ») ; la réponse part par `approval.answer` au nom du propriétaire. Sans réponse
  en 10 min : refus (règle du moteur).
- Photos et documents : enregistrés dans l'instance (`state/core/telegram/inbox/<chat>/`, 0600) et nommés au moteur,
  qui les lit avec ses outils.
- Commandes : `/stop` (interrompt le tour, `turn.cancel`), `/nouveau`, `/etat` (tâche en cours, autorisations en
  attente), `/aide`.

## Fichiers

| Fichier | Contenu |
|---|---|
| `bot.py` | le service (Bot API, client Engine API, état durable, porte) ; `--check` vérifie bot, propriétaire, moteur |
| `tgformat.py` | Markdown → HTML Telegram, découpage, libellés d'outils |
| `tests/test_bot.py` | 11 essais (Telegram et moteur simulés) : `walter-python -m pytest core/interfaces/telegram/tests` |

Réglages : `core/config/telegram.toml` (défauts neutres), surchargés par `@instance/config/core/telegram.toml`
(grant du bot, `owner_ids`, compte). État : `@instance/state/core/telegram/state.json` (offset Telegram, numéros de
conversation, dernier événement vu ; 0600). Unité : `core/systemd/walter-telegram.service` (copiée dans
`/etc/systemd/system`). Aucun secret dans le code, la configuration ou l'unité : jeton du bot par
`walter-secret grant access`, jeton du moteur lu dans l'instance ; aucune URL contenant le jeton n'est journalisée.

## Retour arrière

`systemctl disable --now walter-telegram` : le bot ne répond plus, rien d'autre ne change (les conversations restent
dans le moteur, l'état dans l'instance).
