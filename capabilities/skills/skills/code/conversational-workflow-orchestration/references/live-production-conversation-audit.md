# Audit d’une conversation chatbot en production

## Sources à croiser

1. **Conversation visible** : lire le fil exact vu par l’utilisateur, dans l’ordre chronologique et avec le bon fuseau horaire.
2. **État serveur** : récupérer l’état de session, le brief sérialisé, les projets, les exécutions et les transitions de workflow.
3. **Version déployée** : vérifier que le comportement observé correspond bien au code actuellement en production, pas au checkout local.

Une table de logs agent vide ne prouve pas l’absence d’échange : les callbacks, boutons et parcours guidés peuvent contourner le journal conversationnel principal.

## Invariants UX à vérifier

- Une objection reçoit une réponse adaptée ; elle ne doit pas être seulement concaténée aux notes avant répétition du même récapitulatif.
- Le cadrage collecte ou infère explicitement les prérequis utiles : références/médias, audience, angle, style, format, durée, variantes, CTA et contraintes.
- Toute inférence reste modifiable et visible dans le résumé.
- Le résumé distingue nettement validation du brief, estimation du coût et lancement payant.
- Aucun texte ne suggère un lancement tant que les références/prérequis requis et la confirmation explicite ne sont pas présents.
- Une correction libre au stade du résumé doit mettre à jour l’état concerné ou rouvrir la bonne question, pas polluer `brief_text`.

## Diagnostic minimal

Pour chaque tour, aligner dans un tableau : message utilisateur, réponse bot, état avant/après, transition attendue, transition observée. Classer ensuite le défaut : compréhension, collecte, sérialisation, rendu, garde de validation, ordre du workflow ou décalage de déploiement.
