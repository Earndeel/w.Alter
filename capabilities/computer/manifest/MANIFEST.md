# Walter Computer — piloter le Mac

Observer et manipuler un appareil de {{owner.address}} par actions atomiques sûres, pour ce qui n'existe que dans une application native. L'agent garde le but et le plan ; le module choisit la cible, vérifie les captures et reprend proprement.

**Organisation** : noyau de politique et d'observation, sessions par client (verrou par appareil), transport vers l'appareil enrôlé.

**Utilisation** : `computer_use(session_id, action, arguments)` — `list_apps`, `list_windows`, `capture`, `click`, `type`, `key`, `scroll`, `drag`, `focus_app`, `launch_app`, `open_url`, `targeted_verify`, `wait`, `close`.
1. Capturer l'application exacte avant toute saisie. 2. Vérifier l'effet des actions qui comptent. 3. `close` à la fin.

**Règles** : les autorisations viennent de la politique serveur, jamais des arguments ; client stdio local uniquement.
