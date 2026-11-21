# Walter Secrets — coffre Bitwarden

L'usage de tout le coffre de {{owner.address}} sans qu'aucune valeur secrète n'entre dans un modèle, un journal, un prompt ou une URL.

**Organisation** : accès Bitwarden avec session partagée (`walter-secrets-sync`), API sûre pour les modèles (métadonnées, références), exécution locale, codes reçus par e-mail ou Beeper, autorisations de W.Alter (`walter-secret grants`).

**Utilisation**
1. `secret_search(query, kind)` : trouver l'entrée (métadonnées seulement).
2. `secret_reference(item, field)` : référence sans valeur.
3. En local : `walter-secret exec --bind VAR=<référence> -- <commande>` ; la valeur n'existe que dans le processus lancé. Code reçu : `walter-secret otp <site>`.

**Règles** : jamais `bw unlock` direct ; jamais de secret dans un prompt, une réponse, une URL, un argument ou une unité systemd.
