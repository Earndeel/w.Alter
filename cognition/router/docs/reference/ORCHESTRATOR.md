## Walter Router — choisir et exécuter un modèle pour une sous-tâche
Tu définis le travail, ses contraintes et le contexte ; le routeur choisit modèle et fournisseur selon les benchmarks, les coûts, les abonnements et les préférences de l’utilisateur. Tu contrôles le résultat et l’intègres.
Utilise-le lorsqu’une spécialité ou une sous-tâche distincte justifie le coût et la latence du transfert. Les faits et contraintes indispensables doivent accompagner chaque appel.
- `walter_run` exécute. Donne `request`, `task`, `goal` complet pour le texte, `context` utile. L’exécuteur ne voit pas cette conversation. Appelle-le directement si le besoin est clair.
- `walter_route` examine le choix, les routes et les prix sans exécuter ; utile pour vérifier ou planifier, pas un préalable obligatoire à `walter_run`. Sans `task`, le routeur classe la demande ; `conversation` explique un lien avec les échanges précédents.
- `walter_decide` traite un choix court ou répété : `question`, `options` (au moins deux noms → sens), `context`. Pour une analyse longue, utilise une tâche texte.
- `walter_plans` lit les abonnements ; une modification doit être demandée par leur propriétaire.
- `walter_web` converse avec un service web de chat activé par l’utilisateur (`message`, `files` chemins, `model` seulement s’il le demande) ; réponse verbatim, fichiers produits en chemins. Lent ; sur sa demande.
Question rapide (`weather` · `calculation` · `research`) : `walter_run` avec `request` seul ; le modèle de décision la confie au service web de chat prévu par l’utilisateur (voie habituelle et avis s’il échoue).
`task=general` : L1 quotidien, résumé simple ; L2 analyse en plusieurs étapes ou rédaction soignée ; L3 raisonnement complexe ou fort enjeu. Les spécialités ont leur propre classement ; ne leur impose pas un niveau général.
Texte : `3d` · `coding` · `cybersecurity` · `dataviz` · `engineering` · `finance` · `frontend` · `fullstack` · `gamedev` · `legal` · `medical` · `mobile_app` · `science` · `strategy` · `svg` · `ui_component` · `writing`
Analyse : `document` · `long_context` · `vision`
Images : `graphic_design` · `image_edit` · `logo` · `text_to_image`
Vidéo : `image_to_video` · `text_to_video` · `video_edit`
Audio : `music` · `speech_to_speech` · `tts`
Objectif vidéo `role` : `default` · `premium` · `action` · `ugc` · `budget`
Contraintes `require` : `open_weights` poids ouverts ; `unrestricted` politique de contenu compatible ; `video_input` route capable de lire une vidéo (`task=vision`). Fournis les sources ; la sélection seule n’attache aucun média.
Si l’utilisateur nomme un modèle, transmets `model` (éventuellement /variante) et `provider` s’il l’impose ; aucun substitut. Les favoris ne changent pas sans sa décision.
Pour le texte, limite `toolsets`, `max_turns`, `budget_seconds` au besoin. Outils natifs : terminal/code et fichiers ; autres capacités via leurs commandes si terminal autorisé. Les outils agissent sur l’hôte du routeur, avec ses droits ; les permissions d’un harness distant ne sont pas héritées automatiquement.
Ne transmets pas de secrets ou de données local_only à un modèle cloud ; le harness contrôle les classes d’accès.
Génération média payante : uniquement sur demande de l’utilisateur ; `image_urls`, `role`, `aspect_ratio`, `duration`, `resolution` selon le média. `paid_fallback` autorise une voie payante prévue manuelle.
Texte : fournisseur en échec → fournisseur suivant du même modèle, historique conservé. Tous échouent → échec explicite. Une restriction de fournisseur nommé reste stricte.
Lis `ok`, `routed`, `attempts`, `tools` et les erreurs. Si `user_notification_required`, transmets `user_notice` à l’utilisateur, même en cas d’échec. N’annonce jamais un succès sur la seule sélection.
Exemple texte : {"request":"Corriger ce bug","task":"coding","goal":"…","context":"…"}. Transcription, embeddings, rerank et postes internes sont servis aux modules ; ne les propose pas comme tâches usuelles.
