# Registre des tâches et poids des benchmarks

> Généré par `walter-router docs --write`. Modifier les sources, puis régénérer ; ne pas éditer ce fichier.


Les postes `internal=true` servent aux modules. Une capacité annoncée ou une offre existante ne prouve pas que le chemin d’exécution accepte toutes ses entrées. Voir EXECUTION.md. Les descriptions et exigences reflètent le registre SQL : certaines mentions de consommateurs historiques ne prouvent pas que ces services sont encore actifs. Les formes d’adresse au propriétaire sont neutralisées dans cet export public.

| Clé | Interface | Interne | Objectif | Description / exigences |
|---|---|---|---|---|
| `3d` | chat | False | best_available | Design Arena 3D ; {} |
| `calculation` | tool | False | tool | Calcul déterministe ; {} |
| `coding` | chat | False | best_available | Arena coding + BridgeBench (vibe coding) + Arena webdev ; {} |
| `cybersecurity` | chat | False | best_available | Sécurité informatique : audit de code, vulnérabilités, analyse d'incident, durcissement. AA Cyber Index. ; {} |
| `dataviz` | chat | False | best_available | Design Arena Data Viz ; {} |
| `decision` | decisions | True | best_available | AA Decision Index: classification, tool-calling decisions (When2Call), knowledge with "I don't know" (non-hallucination), reasoning; speed and cost per 1M tasks ; {} |
| `decision_vision` | decisions | True | best_available | Decision models that also read images (OpenRouter input modalities). AA Decision Index has no vision test yet: ranked on the text index, filtered on image input. ; {} |
| `devboard_reading` | chat | True | best_available | Lire un condensé de session d'agent ou une décision et en tirer chantiers, états, accords et remplacements, en JSON fidèle avec preuves. ; {"min_context": 128000, "structured_output": true} |
| `document` | chat | False | best_available | Arena Document ; {} |
| `embeddings` | embedding | True | best_available | Vecteurs de la mémoire : qualité de recherche (ELO Agentset) et recherche en français (MTEB MIRACL fr) ; seuls les modèles mesurés sur le classement principal sont rangés (revectoriser ne se décide pas sur un seul test). Changer de modèle oblige à revectoriser toute la banque : jamais sans l'accord du propriétaire. ; {"on_change": "Changer de modèle d'embeddings = revectoriser tout l'index de la mémoire : opération lourde, à planifier avec le propriétaire de l'instance ; l'ancien modèle reste en place tant que ce n'est pas fait.", "require_primary": true, "revectorize_on_change": true} |
| `engineering` | chat | False | best_available | Travail d'ingénieur : analyse de conception, calculs techniques, normes, documentation technique. AA Engineering Index. ; {} |
| `finance` | chat | False | best_available | Comptabilité, analyse financière, fiscalité, prévisions et analyse économique quantitative. AA Finance & Accounting et Economics Index. ; {} |
| `frontend` | chat | False | best_available | Design Arena Website ; {} |
| `fullstack` | chat | False | best_available | Design Arena agents Full-Stack ; {} |
| `gamedev` | chat | False | best_available | Design Arena Game Dev ; {} |
| `general` | chat | False | value | Résumé, actualité, analyse, comparatif, rédaction ; {} |
| `graphic_design` | image | False | best_available | Design Arena Graphic Design ; {} |
| `image_edit` | image | False | best_available | Arena Image Edit ; {} |
| `image_to_video` | video | False | best_available | AA Image-to-Video Arena ; {} |
| `legal` | chat | False | best_available | Questions juridiques et travail d'avocat : contrats, litiges, réglementation. AA Legal Index + Harvey LAB. ; {} |
| `logo` | image | False | best_available | Design Arena Logo ; {} |
| `long_context` | chat | False | best_available | Raisonner sur un très long contexte : livre, base documentaire, plusieurs gros documents, long historique. ; {} |
| `medical` | chat | False | best_available | Questions de santé : symptômes, maladies, médicaments, lecture de résultats. AA Healthcare & Medical Index + HealthBench. ; {} |
| `memory_extraction` | chat | True | level | Extraire faits, entités, préférences et liens d'un texte en JSON fidèle (rétention, consolidation, profil). ; {"level": "L1", "min_context": 128000, "structured_output": true} |
| `mobile_app` | chat | False | best_available | Design Arena agents Mobile Apps ; {} |
| `music` | music | False | best_available | Aucun classement collecté : choix sur offres uniquement Classé sur AA Music (chant et instrumental). ; {} |
| `rerank` | rerank | True | best_available | Réordonner les souvenirs trouvés avant de les donner au modèle (rappel mémoire, voix) : qualité de classement (ELO Agentset) puis latence ; au-delà de 0,7 s mesurés, un modèle est exclu (budget du rappel vocal). ; {"max_latency_s": 0.7, "on_change": "Hindsight garde son reranker dans le drop-in statique 20-reranker-fallback.conf : à modifier à la main après adoption ; walter-memory et walter-voice-memory suivent pick rerank."} |
| `research` | tool | False | tool | Recherche web + synthèse par le niveau général ; {} |
| `science` | chat | False | best_available | Problèmes scientifiques de niveau recherche : physique, chimie, biologie, mathématiques, calcul scientifique. ; {} |
| `speech_to_speech` | audio | False | best_available | AA Speech to Speech Index ; {} |
| `strategy` | chat | False | best_available | Travail de consultant : stratégie d'entreprise, organisation, opérations, analyse de marché. AA Strategy & Ops Index. ; {} |
| `stt` | transcription | True | best_available | Transcrire les messages vocaux du propriétaire, dans sa langue : fidélité d'abord (AA-WER, mesuré en anglais : AA ne publie pas de résultat français), puis vitesse. Modèles de transcription et modèles de chat qui entendent l'audio. ; {"language": "fr", "on_change": "Adopter un modèle de transcription dédié (Whisper, MAI, Scribe…) : le plugin Hermes gemini-stt appelle aujourd'hui chat/completions avec input_audio ; il devra appeler l'API de transcription d'OpenRouter."} |
| `summarization` | chat | True | level | Résumer fidèlement un long contexte (conversation, journal) sans rien inventer : tâche de fond, volume élevé. ; {"level": "L1", "min_context": 256000} |
| `svg` | chat | False | best_available | Design Arena SVG ; {} |
| `text_to_image` | image | False | best_available | AA Text-to-Image Arena ; {} |
| `text_to_video` | video | False | best_available | AA Text-to-Video Arena ; {} |
| `tts` | audio | False | best_available | AA Provider Voice Elo ; {} |
| `ui_component` | chat | False | best_available | Design Arena UI Component ; {} |
| `video_edit` | video | False | best_available | Arena Video Edit ; {} |
| `vision` | chat | False | best_available | Arena Vision ; {} |
| `voice_assist` | chat | True | best_available | Tri, réponse directe et résumé à dire pendant un appel téléphonique : la latence prime, puis le français et la fiabilité. ; {"max_latency_s": 3, "reasoning": "minimal", "require_primary": true, "structured_output": true} |
| `weather` | tool | False | tool | Outil météo, pas de LLM ; {} |
| `writing` | chat | False | best_available | Textes soignés : articles, histoires, discours, textes créatifs, réécriture de style. Classé sur Arena (écriture créative, français). ; {} |

## Affectation des benchmarks

| Tâche | Famille | Sous-classement | Principal | Poids | Note |
|---|---|---|---|---|---|
| 3d | aa_eval | aa_3d | false | 0.2 | AA-3D : scènes 3D construites par des agents |
| 3d | arena | webdev | false | 0.2 | — |
| 3d | bridgebench | frontend | false | 0.1 | — |
| 3d | da_models | 3d | true | 0.5 | — |
| coding | arena | text_coding | true | 0.3 | — |
| coding | arena | webdev | false | 0.2 | — |
| coding | bridgebench | backend | false | 0.15 | — |
| coding | bridgebench | overall | false | 0.35 | — |
| cybersecurity | aa_eval | cyber | true | 1.0 | AA Cyber Index |
| dataviz | arena | webdev | false | 0.25 | — |
| dataviz | bridgebench | frontend | false | 0.15 | — |
| dataviz | da_models | dataviz | true | 0.6 | — |
| decision | aa_decision | decision | true | 1.0 | AA Decision Index v1.0 |
| decision_vision | aa_decision | decision | true | 1.0 | AA Decision Index v1.0 (no vision eval yet) |
| document | arena | document | true | 1.0 | — |
| embeddings | agentset | embeddings | true | 0.5 | qualité de recherche RAG (ELO par paires) |
| embeddings | mteb | retrieval_fr | false | 0.5 | recherche en français (MIRACL fr, nDCG@10) |
| engineering | aa_eval | idx_engineering | true | 1.0 | AA Engineering Index |
| finance | aa_eval | idx_economics | false | 0.3 | AA Economics Index |
| finance | aa_eval | idx_finance | true | 0.7 | AA Finance & Accounting Index |
| frontend | arena | webdev | false | 0.3 | — |
| frontend | bridgebench | frontend | false | 0.25 | — |
| frontend | da_models | website | true | 0.45 | — |
| fullstack | arena | webdev | false | 0.2 | — |
| fullstack | bridgebench | backend | false | 0.2 | — |
| fullstack | bridgebench | overall | false | 0.2 | — |
| fullstack | da_agents | fullstack | true | 0.4 | — |
| gamedev | arena | webdev | false | 0.25 | — |
| gamedev | bridgebench | frontend | false | 0.15 | — |
| gamedev | da_models | gamedev | true | 0.6 | — |
| general | aa_intelligence | intelligence | true | 0.5 | — |
| general | arena | text | false | 0.2 | — |
| general | arena | text_french | false | 0.2 | — |
| general | bridgebench | overall | false | 0.1 | BridgeBench global |
| graphic_design | arena | text_to_image | false | 0.3 | — |
| graphic_design | da_models | graphicdesign | true | 0.7 | — |
| image_edit | arena | image_edit | true | 1.0 | — |
| image_to_video | aa_mm | image_to_video | true | 0.5 | — |
| image_to_video | arena | image_to_video | false | 0.5 | — |
| legal | aa_eval | harvey_lab | false | 0.4 | Harvey LAB : tâches réelles d'avocats (critères tous validés) |
| legal | aa_eval | idx_legal | true | 0.6 | AA Legal Index |
| logo | arena | text_to_image | false | 0.3 | — |
| logo | da_models | logo | true | 0.7 | — |
| long_context | aa_eval | lcr | true | 1.0 | AA-LCR : raisonnement sur ~100k tokens de documents |
| medical | aa_eval | healthbench | false | 0.2 | HealthBench : questions de santé du grand public |
| medical | aa_eval | healthbench_pro | false | 0.3 | HealthBench Professional : cas cliniques de professionnels |
| medical | aa_eval | idx_medical | true | 0.5 | AA Healthcare & Medical Index |
| mobile_app | arena | webdev | false | 0.2 | — |
| mobile_app | bridgebench | overall | false | 0.2 | — |
| mobile_app | da_agents | mobileapps | true | 0.6 | — |
| music | aa_mm | music_instrumental | false | 0.5 | AA Music instrumental |
| music | aa_mm | music_vocals | true | 0.5 | AA Music chant |
| rerank | agentset | rerank | true | 0.7 | qualité de classement RAG (ELO par paires) |
| rerank | agentset | rerank_speed | false | 0.3 | latence : budget du rappel vocal 0,7 s |
| science | aa_eval | critpt | true | 0.35 | CritPt : physique de niveau recherche |
| science | aa_eval | gpqa | false | 0.35 | GPQA Diamond : questions de doctorat |
| science | aa_eval | hle | false | 0.15 | Humanity's Last Exam |
| science | aa_eval | scicode | false | 0.15 | SciCode : calcul scientifique |
| speech_to_speech | aa_mm | speech_to_speech | true | 1.0 | — |
| strategy | aa_eval | idx_strategy_ops | true | 1.0 | AA Strategy & Ops Index |
| stt | aa_stt | speed | false | 0.25 | vitesse (facteur temps réel) : messages vocaux transcrits sans attendre |
| stt | aa_stt | wer | true | 0.75 | fidélité de transcription (AA-WER, anglais) |
| svg | arena | webdev | false | 0.4 | — |
| svg | da_models | svg | true | 0.6 | — |
| text_to_image | aa_mm | text_to_image | true | 0.5 | — |
| text_to_image | arena | text_to_image | false | 0.5 | — |
| text_to_video | aa_mm | text_to_video | true | 0.5 | — |
| text_to_video | arena | text_to_video | false | 0.5 | — |
| tts | aa_mm | tts | true | 1.0 | — |
| ui_component | arena | webdev | false | 0.3 | — |
| ui_component | bridgebench | frontend | false | 0.25 | — |
| ui_component | da_models | uicomponent | true | 0.45 | — |
| video_edit | arena | video_edit | true | 1.0 | — |
| vision | aa_eval | mmmu_pro | false | 0.4 | MMMU-Pro : raisonnement sur images |
| vision | arena | vision | true | 0.6 | — |
| voice_assist | arena | text_french | false | 0.3 | Classement en français : la langue de l'instance |
| voice_assist | bridgebench | speed | true | 0.5 | latence d'un appel vocal |
| voice_assist | bridgebench | trustworthiness | false | 0.2 | ne rien inventer au téléphone |
| writing | arena | text_creative | true | 0.6 | Arena écriture créative (votes humains) |
| writing | arena | text_french | false | 0.4 | le propriétaire écrit en français |
