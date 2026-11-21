# Walter Secrets — guide détaillé

## Objectif

Donner aux agents l'usage du coffre Bitwarden complet de {{owner.address}} sans qu'aucune valeur secrète n'entre dans un
modèle, un journal, un prompt ou une URL. Un agent s'en sert pour trouver un identifiant, une clé ou une carte et
l'utiliser dans une commande locale, ou pour récupérer un code reçu par e-mail ou Beeper.

## Comment l'utiliser

1. `secret_search(query, kind)` : métadonnées et identifiants d'entrées, jamais de mot de passe, token, OTP ou cookie.
   `kind` = login, card, identity, note, ssh_key.
2. `secret_reference(item, field)` : référence `walter-secret://bitwarden/<uuid>/<champ>` sans valeur. Une
   référence est un pointeur, pas une autorisation.
3. Exécution locale : `walter-secret exec --bind VAR=<référence> -- <commande>` ; la valeur n'existe que dans
   l'environnement du processus lancé, qui hérite des permissions du harness. Sa sortie est jetée.

## Organisation

| Partie | Rôle |
|---|---|
| `walter_secrets/vault.py` | Accès Bitwarden, métadonnées, pièces jointes, audit |
| `walter_secrets/service.py` | API v1 sûre pour les modèles (search, reference) et exécution locale |
| `walter_secrets/masking.py` | Masquage partagé, erreurs publiques sans texte d'exception |
| `walter_secrets/unlock.py` | Déverrouillage depuis le coffre local chiffré age (session partagée) |
| `walter_secrets/otp.py` | Codes reçus : Gmail (connecteur Walter Memory), Beeper |
| `secrets_sync.py`, `vault_react.py` | Surveillance du coffre, application aux cibles, sauvegarde chiffrée |
| `ports/hermes/` | Outils `secret_*`, crochets et remplissage de formulaires dans le navigateur Hermes |
| `walter-secret grants` | Autorisations de W.Alter sur les comptes et services |

## Interfaces

| Besoin | MCP | Hermes | CLI locale |
|---|---|---|---|
| Trouver | `secret_search` | `secret_*` | `walter-secret search` |
| Référencer | `secret_reference` | `secret_*` | `walter-secret ref` |
| Utiliser | — | substitution de l'adaptateur Hermes | `walter-secret exec --bind …` |

## Règles et limites

- Ne jamais lancer `bw unlock` directement : la session est partagée par `walter-secrets-sync`.
- Jamais de secret dans une unité systemd, une URL, un argument de commande ou une réponse.
- La substitution Hermes ne fonctionne que dans Hermes ; ailleurs, `walter-secret exec`.
- Rotation du mot de passe maître en attente (fuite du 2026-10-22).
