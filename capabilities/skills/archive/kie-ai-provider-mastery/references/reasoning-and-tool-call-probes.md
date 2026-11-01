# Kie.ai — interprétation des probes de raisonnement et de tool use

## Portée

Référence de diagnostic pour les probes Kie multi-protocoles. Elle sépare le texte visible, les compteurs d’usage et les appels d’outils réellement observés.

## Raisonnement rapporté

`reasoning_tokens`, `thinkingTokenCount` et `output_tokens_details.reasoning_tokens` sont des métriques opaques déclarées par l’adaptateur. Elles ne donnent pas accès au contenu du raisonnement et ne doivent pas être présentées comme une chaîne de pensée récupérée.

- Un compteur positif confirme que l’adaptateur a déclaré des tokens internes.
- Un compteur à zéro est seulement une observation ; l’adaptateur peut omettre ou normaliser le champ.
- Conserver le champ brut et séparer systématiquement fait observé et interprétation.

## Tool calls

Un probe sans champ `tools` ne teste pas réellement la capacité d’appel d’outils. Il faut fournir un schéma d’outil et inspecter le flux :

- Responses (Grok/Luna) : `function_call` dans les output items, arguments fragmentés si streaming, puis `function_call_output` renvoyé côté client. Vérifier le préfixe Kie attendu pour le `call_id` (`fc_` sur certains flux).
- Anthropic Messages (Claude/Opus) : bloc `tool_use` dans `content_block_start`, fragments `input_json_delta`, puis `tool_result` dans le message utilisateur.
- Gemini natif : `functionCall` dans `candidates[].content.parts[]`.
- Gemini OpenAI-compatible : `tool_calls` dans `choices[].delta`.

Distinguer les outils serveur Kie (`num_server_side_tools_used`, `server_tool_use`) des fonctions client Hermes. L’absence de `function_call`, `tool_use` ou `tool_calls` dans un prompt sans outils signifie seulement qu’aucun appel n’a été demandé/observé, pas que le modèle ne sait pas utiliser les outils.

## Rapport minimal requis

Conserver le SSE brut, `Content-Type`, événements, réponse finale, usage, crédits et latence. Déclarer séparément : texte reçu, raisonnement reporté, tool calls observés, outils serveur comptabilisés et limites d’inférence. Rejouer un probe dédié avec schéma d’outil avant de conclure sur le tool use.

## Exemple de lecture

Sur un probe minimal Kie : Grok peut rapporter un nombre positif de `reasoning_tokens` tout en n’ayant aucun outil serveur utilisé ; Luna peut rapporter `effort=low` et zéro token de raisonnement ; Opus peut exposer `web_search_requests=0` et `web_fetch_requests=0`. Ces valeurs décrivent ce flux précis et ne constituent pas une garantie générale du fournisseur.
