# Constantes, environnement et configuration livrée

> Généré par `walter-router docs --write`. Modifier les sources, puis régénérer ; ne pas éditer ce fichier.


Inventaire exhaustif des affectations littérales MAJUSCULES au niveau module et des noms de variables d’environnement lus explicitement. Les constantes ne sont pas toutes des réglages utilisateur. Les expressions calculées, paramètres locaux et métadonnées externes sont décrits par le code et les contrats d’usage.

| Source | Constante | Valeur | Commentaire source |
|---|---|---|---|
| analysis/alerts.py | `UNRANKED_DAYS` | 30 |  |
| analysis/alerts.py | `TOP_N` | 3 |  |
| analysis/alerts.py | `RAW_MEASURES` | [["latency", "latency_ms", "ms"], ["WER", "wer_pct", "% WER"]] |  |
| analysis/aliases_admin.py | `MIN_SIMILARITY` | 0.6 | below: a rename (Hailuo 3 = MiniMax H3) — accepted only with a source URL in the reason |
| analysis/catalog.py | `UNIT_SHORT` | {"per 1000 characters": "$/1k car.", "per 1m tokens": "$/M tokens", "per image": "$/img", "per minute": "$/min", "per request": "$/requête", "per search": "$/recherche", "per second": "$/s", "per song": "$/titre"} |  |
| analysis/catalog.py | `PROVIDERS` | {"codex": "Codex", "google-flow": "Flow", "kie": "Kie", "openrouter": "OpenRouter"} |  |
| analysis/catalog.py | `BOARDS` | {"aa_decision": "AA Decision", "aa_eval": "AA", "aa_intelligence": "AA", "aa_mm": "AA", "aa_stt": "AA STT", "agentset": "Agentset", "arena": "Arena", "bridgebench": "BridgeBench", "da_agents": "Design Arena", "da_models": "Design Arena", "mteb": "MTEB"} |  |
| analysis/catalog.py | `MAX_LISTED_RESOLUTIONS` | 4 |  |
| analysis/catalog.py | `ICONS` | {"audio": "🗣️", "chat": "💬", "embedding": "🧭", "image": "🖼️", "music": "🎵", "rerank": "🔀", "transcription": "🎙️", "video": "🎬"} |  |
| analysis/changes.py | `MIN_GAP_H` | 24 |  |
| analysis/changes.py | `PRICE_DROP` | 0.15 |  |
| analysis/changes.py | `NERF` | {"aa_decision": 2.0, "aa_eval": 3.0, "aa_intelligence": 2.0, "aa_stt:speed": 50.0, "aa_stt:wer": 1.0, "agentset:embeddings_speed": 0.5, "agentset:rerank_speed": 0.5, "bridgebench": 30.0, "mteb": 2.0} | Elo-type boards: NERF_ELO |
| analysis/changes.py | `NERF_ELO` | 15.0 |  |
| analysis/changes.py | `BENCH_KINDS` | ["aa", "aa_eval", "aa_decision", "mm", "da", "arena", "bridgebench", "aa_stt", "agentset", "mteb"] |  |
| analysis/changes.py | `OFFER_KINDS` | ["openrouter", "kie", "hermes_providers"] |  |
| analysis/changes.py | `INTELLIGENCE` | aa_intelligence:intelligence |  |
| analysis/decision_pareto.py | `FREE` | {"clef": "Workers AI (allocation gratuite)", "clef-flash": "Workers AI (allocation gratuite)", "mercury-decide": "OpenRouter :free"} |  |
| analysis/dossier.py | `RULES` | ["1. Les favoris de {owner} priment : choisir le rôle qui correspond à l'objectif de la demande (signaux), sinon le rôle « default ».", "2. Sans favori : prendre le premier candidat (score composite pondéré multi-benchmarks).", "3. Égalité (écart dans la marge) : préférence de {owner}, puis accès par abonnement (Codex, crédits Flow).", "4. Workflow d'un modèle (références, prompt adapté…) : le planifier avant de générer.", "5. Demande sans restriction : uniquement un modèle 'unrestricted' (ou 'permissive' avec avertissement).", "6. Ne jamais changer un favori sans l'accord de {owner}."] |  |
| analysis/identity.py | `TIERS` | ["non-reasoning", "minimal", "low", "medium", "high", "xhigh", "max"] |  |
| analysis/identity.py | `VENDOR_PREFIXES` | ["google-", "openai-", "anthropic-", "meta-", "microsoft-", "alibaba-", "bytedance-", "black-forest-labs-"] |  |
| analysis/identity.py | `BENCHMARK_NAMESPACES` | ["aa", "aa_eval", "aa_decision", "da", "mm", "arena", "bridgebench", "aa_stt", "agentset", "mteb"] |  |
| analysis/identity.py | `_AGENTSET_VENDORS` | ["cohere-", "voyage-ai-", "baai-", "openai-"] | 'Cohere Rerank 4 Pro' -> rerank-4-pro (API id) |
| analysis/ingest.py | `NAME_PRIORITY` | {"aa": 3, "aa_stt": 9, "agentset": 10, "arena": 6, "bridgebench": 5, "da": 8, "hermes_providers": 2, "kie": 7, "mm": 4, "mteb": 11, "openrouter": 1} |  |
| analysis/knowledge.py | `TIE_MARGIN` | {"AA Intelligence Index": 1.0, "Composite /100": 1.5} | score points inside which two models are a tie |
| analysis/knowledge.py | `ELO_TIE` | 10.0 | Elo boards (Arena, AA arenas, Design Arena) |
| analysis/media.py | `NORM_UNITS` | {"audio": "per 1000 characters", "embedding": "per 1m tokens", "image": "per image", "music": null, "rerank": "per search", "transcription": "per minute", "video": "per second"} |  |
| analysis/media.py | `MODE_LABELS` | {"i2i": "image→image", "i2v": "image→vidéo", "r2v": "référence→vidéo", "t2i": "texte→image", "t2v": "texte→vidéo", "v2v": "vidéo→vidéo"} |  |
| analysis/parse.py | `MM_TASKS` | {"index": "speech_to_speech", "provider_voice": "tts"} |  |
| analysis/parse.py | `KIE_DIMENSION_FIXES` | {"('claude-opus-5-5', 'claude-opus-5')": "output"} |  |
| analysis/parse.py | `OR_BASE_UNITS` | {"/1K calls": "per call", "/M UTF-8 bytes": "per utf-8 byte", "/M characters": "per character", "/M tokens": "per token", "/minute": "per second"} |  |
| analysis/parse.py | `OFFER_KINDS` | ["openrouter", "kie", "codex", "claude_pro", "antigravity", "declared", "hermes_providers"] |  |
| analysis/postes.py | `BOARDS` | {"agentic": ["arena", "agent"], "intelligence": ["aa_intelligence", "intelligence"], "reliability": ["bridgebench", "trustworthiness"], "speed": ["bridgebench", "speed"]} |  |
| analysis/scoring.py | `SHRINK_K` | 0.25 |  |
| analysis/scoring.py | `FEEDBACK_POINTS` | 3.0 | per net rating point from the owner on that task (capped at +/-3 -> +/-9 composite points) |
| analysis/scoring.py | `VOTES_HALF` | 500.0 |  |
| analysis/select.py | `DEFAULT_EFFORTS` | ["medium", "high"] | assumed effort when a leaderboard lists a model without one (flagged) |
| analysis/select.py | `BENCH_KIND` | {"aa_decision": "aa_decision", "aa_eval": "aa_eval", "aa_intelligence": "aa", "aa_mm": "mm", "aa_stt": "aa_stt", "agentset": "agentset", "arena": "arena", "bridgebench": "bridgebench", "da_agents": "da", "da_models": "da", "mteb": "mteb"} |  |
| analysis/select.py | `BOARD_GRACE_DAYS` | 21 |  |
| analysis/select.py | `MEDIA_EXEC_INTERFACES` | ["image", "video", "audio", "music"] |  |
| analysis/select.py | `LEVEL_WORDS` | ["high", "latest", "low", "max", "medium", "minimal", "preview", "xhigh"] |  |
| analysis/telegram.py | `ROLE_LABELS` | {"action": "action", "budget": "budget", "default": "défaut", "premium": "premium", "ugc": "UGC", "value": "ratio"} |  |
| analysis/telegram.py | `SHORT_TASK` | {"decision": "Routage d’intention", "decision_vision": "Décision avec image"} |  |
| analysis/telegram.py | `BOARD_TASKS` | {"3d": "3D", "decision": "", "embeddings": "embeddings (ELO)", "embeddings_speed": "embeddings latence", "frontend": "front-end", "image_edit": "retouche d'image", "image_to_video": "animation d'image", "intelligence": "intelligence", "music": "musique", "rerank": "rerank (ELO)", "rerank_speed": "rerank latence", "retrieval_fr": "recherche en français", "speed": "vitesse", "text": "texte", "text_coding": "code", "text_to_image": "image", "text_to_video": "vidéo depuis texte", "tts": "voix", "webdev": "web", "wer": "fidélité (100 − WER)"} |  |
| analysis/telegram.py | `BUTTONS` | {"board_down": [["👁️ Vu", "d"]], "challenger": [["✅ Changer", "a"], ["✖️ Garder l'actuel", "d"]], "nerf": [["👁️ Masquer", "d"]], "new_best": [["✅ Passer au nouveau", "a"], ["✖️ Garder l'actuel", "d"]], "pareto": [["👍 Noté", "a"], ["✖️ Ignorer", "d"]], "plan_change": [["✅ Mettre à jour", "a"], ["✖️ Ignorer", "d"]], "tier": [["✅ Changer", "a"], ["✖️ Garder l'actuel", "d"]]} |  |
| analysis/tiers.py | `QUALITY_FLOOR` | 35.0 |  |
| analysis/tiers.py | `CEILING_BAND` | 5.0 |  |
| analysis/tiers.py | `KNEE_DROP` | 2.0 |  |
| guardian/checks.py | `RUN_MAX_AGE_H` | 54 | the cycle runs every 48 h |
| guardian/checks.py | `TEST_TIMEOUT` | 600 |  |
| guardian/repair.py | `LEVEL` | L2 |  |
| guardian/repair.py | `MAX_TURNS` | 80 |  |
| guardian/repair.py | `BUDGET_S` | 2400 |  |
| guardian/repair.py | `ALLOWED` | ["research/", "analysis/parse.py", "analysis/identity.py", "analysis/aliases.json", "interface/", "tests/"] |  |
| guardian/run.py | `MAX_ATTEMPTS` | 3 | agent runs per incident before it is handed to the owner |
| guardian/run.py | `RETRY_AFTER_H` | 12 | between two agent runs on the same incident |
| guardian/run.py | `TEST_GRACE_H` | 6 | a failing test is often someone's work in progress: act only if it lasts |
| guardian/run.py | `MAX_REPAIRS_PER_PASS` | 3 |  |
| guardian/run.py | `EXTERNAL_NOTICE_H` | 48 | an outside outage is worth a message only when it lasts this long |
| guardian/run.py | `_CLOSED_OK` | ["fixed", "resolved"] |  |
| guardian/run.py | `DOCS_OWNER_AFTER_H` | 24 | a reference that cannot be regenerated for a day goes to the owner |
| health.py | `RUN_MAX_AGE_H` | 54 | the cycle runs every 48 h |
| hermes-plugins/kie-compat/__init__.py | `KIE_ANTHROPIC` | api.kie.ai/claude |  |
| hermes-plugins/walter-router/__init__.py | `CHILD_ENV` | WALTER_ROUTER_CHILD | set by the router in a sub-agent run: no recursive routing |
| hermes-plugins/walter-router/__init__.py | `ALLOWED_TOOLSETS` | ["web", "walter-web", "file", "terminal", "vision", "skills", "code_execution", "memory"] |  |
| hermes-plugins/walter-router/__init__.py | `FALLBACK_TASKS` | ["general", "coding", "frontend", "ui_component", "3d", "gamedev", "dataviz", "svg", "fullstack", "mobile_app", "vision", "document", "text_to_image", "image_edit", "logo", "graphic_design", "text_to_video", "image_to_video", "video_edit", "tts", "speech_to_speech", "music", "weather", "calculation", "research"] |  |
| hermes-plugins/walter-router/__init__.py | `REQUIRE` | ["unrestricted", "open_weights", "video_input"] |  |
| hermes-plugins/walter-router/__init__.py | `DECISION` | ["model", "provider", "task", "level", "require", "conversation"] |  |
| hermes-plugins/walter-router/__init__.py | `DECIDE_SCHEMA` | {"description": "The router's decision model for a quick choice of your own: sort, yes/no, pick one of several options, many times over (a fraction of a second, a fraction of a cent). Returns the choice, its confidence and the probabilities.", "name": "walter_decide", "parameters": {"properties": {"context": {"description": "The data to judge (a message, an excerpt…).", "type": "string"}, "options": {"additionalProperties": {"type": "string"}, "description": "Option name -> what it means (at least two).", "type": "object"}, "question": {"type": "string"}}, "required": ["question", "options"], "type": "object"}} |  |
| hermes-plugins/walter-router/__init__.py | `VERDICT_SCHEMA` | {"description": "The owner's answer to a Walter Router Telegram message (« adopter 1 », « ignorer 2 », « adopter 1 action »): adopting a new model pins it for the roles it beats (or only the named role); adopting a text tier pins it; ignoring a new #1 keeps the previous model.", "name": "walter_verdict", "parameters": {"properties": {"alert_id": {"description": "The short number shown in the message (1, 2, 3…).", "type": "integer"}, "decision": {"enum": ["adopter", "ignorer"], "type": "string"}, "note": {"type": "string"}, "role": {"description": "Optional role named by the owner (premium, action, ugc, budget, default, L1, L2, L3).", "type": "string"}}, "required": ["alert_id", "decision"], "type": "object"}} |  |
| hermes-plugins/walter-router/__init__.py | `PLANS_SCHEMA` | {"description": "The owner's AI subscriptions as Walter Router knows them (ChatGPT Plus, Claude Pro, Google AI Pro…): list them, or record a change he tells you about (new plan, price, end of an offer, models included) or a cancellation. Plan ids are lowercase with dashes (openai-plus, google-ai-pro). Only on his word: never invent a plan or a price.", "name": "walter_plans", "parameters": {"properties": {"action": {"enum": ["list", "set", "retire"], "type": "string"}, "models": {"items": {"type": "string"}, "type": "array"}, "note": {"type": "string"}, "plan": {"type": "string"}, "plan_id": {"type": "string"}, "price_usd_month": {"type": "number"}, "since": {"description": "YYYY-MM-DD", "type": "string"}, "until": {"description": "YYYY-MM-DD", "type": "string"}, "vendor": {"type": "string"}, "why": {"description": "His words, short.", "type": "string"}}, "required": ["action"], "type": "object"}} |  |
| hermes-plugins/walter-router/__init__.py | `HERMES_RULES` | Walter Router dans Hermes : pour générer une image, une vidéo, une musique ou une voix, appelle walter_run avec la demande mot pour mot (via tool_call si l'outil est différé). Ses favoris et objectifs priment sur tout skill propre à un modèle ; un skill sert ensuite à exécuter le modèle choisi. Quand l'utilisateur répond « adopter N » ou « ignorer N » à une alerte Walter Router, appelle walter_verdict ; quand il juge le résultat d'un modèle (« nul », « parfait »…), walter_feedback ; quand il parle d'un changement d'abonnement IA (nouveau forfait, prix, fin d'offre, résiliation), walter_plans. |  |
| hermes-plugins/walter-router/__init__.py | `WEB_SCHEMA` | {"description": "Talk to a web chat service the owner enabled (Walter Router rule, his browser session, no Walter LLM): the message goes as is, the reply comes back verbatim. service omitted = the only enabled one. model ONLY when the owner asks (words of the service's own picker: a model name and/or a reasoning level); omitted = the model already selected there, nothing is changed. files = local paths attached; produced images/files come back as local paths in files[].path (send them with MEDIA:<path>). Slow (seconds to minutes): only when he asks for that service or what it alone does.", "name": "walter_web", "parameters": {"properties": {"conversation": {"description": "named thread kept across calls (default: default)", "type": "string"}, "files": {"description": "local paths, max 10, 50 MB each", "items": {"type": "string"}, "type": "array"}, "message": {"type": "string"}, "model": {"description": "only if the owner names one", "type": "string"}, "request_id": {"description": "idempotent: a retry returns the same answer", "type": "string"}, "service": {"description": "omit = the only enabled service", "type": "string"}, "timeout_s": {"maximum": 600, "minimum": 1, "type": "integer"}}, "required": ["message"], "type": "object"}} |  |
| instance.py | `NEUTRAL_OWNER` | l'utilisateur | only when no instance answers |
| interface/library.py | `PROV` | {"antigravity": "Antigravity (AI Pro)", "arnict": "Arnict", "claude-pro": "Claude Pro", "codex": "Codex (abonnement)", "google-flow": "Flow", "kie": "Kie", "kie-codex": "Kie", "openai-codex": "Codex (abonnement)", "openrouter": "OpenRouter", "venice": "Venice"} |  |
| interface/library.py | `MODES` | {"graphic_design": "t2i", "image_edit": "i2i", "image_to_video": "i2v", "logo": "t2i", "music": "music", "text_to_image": "t2i", "text_to_video": "t2v", "tts": "tts", "video_edit": "v2v"} |  |
| interface/library.py | `IMAGE_TOKENS` | [1056, 4160] | medium / high 1024x1024 output tokens (OpenAI gpt-image token tables) |
| interface/library.py | `ROLE_ORDER` | case p.role when 'default' then 0 when 'L1' then 0 when 'L2' then 1 when 'L3' then 2 else 5 end |  |
| interface/library.py | `SERVICE_UNITS` | {"per 1m tokens": "$/M tokens", "per hour": "$/h", "per minute": "$/min", "per search": "$/recherche"} |  |
| interface/library.py | `BENCH_TASK` | {"3d": ["3D", "3D"], "aa_3d": ["AA-3D", "AA-3D"], "backend": ["back-end", "back-end"], "critpt": ["CritPt (physique)", "CritPt (physics)"], "cyber": ["Cyber Index", "Cyber Index"], "dataviz": ["dataviz", "dataviz"], "decision": ["Decision Index", "Decision Index"], "document": ["documents", "documents"], "embeddings": ["qualité", "quality"], "frontend": ["front-end", "front-end"], "fullstack": ["full-stack", "full-stack"], "gamedev": ["jeux", "games"], "gpqa": ["GPQA Diamond", "GPQA Diamond"], "graphicdesign": ["graphisme", "graphic design"], "harvey_lab": ["Harvey LAB (juridique)", "Harvey LAB (legal)"], "healthbench": ["HealthBench", "HealthBench"], "healthbench_pro": ["HealthBench Professional", "HealthBench Professional"], "hle": ["Humanity's Last Exam", "Humanity's Last Exam"], "idx_economics": ["Economics Index", "Economics Index"], "idx_engineering": ["Engineering Index", "Engineering Index"], "idx_finance": ["Finance & Accounting Index", "Finance & Accounting Index"], "idx_legal": ["Legal Index", "Legal Index"], "idx_medical": ["Healthcare & Medical Index", "Healthcare & Medical Index"], "idx_strategy_ops": ["Strategy & Ops Index", "Strategy & Ops Index"], "image_edit": ["retouche d'image", "image editing"], "image_to_video": ["animation d'image", "image to video"], "intelligence": ["Intelligence Index", "Intelligence Index"], "lcr": ["long contexte (LCR)", "long context (LCR)"], "logo": ["logo", "logo"], "mmmu_pro": ["MMMU-Pro", "MMMU-Pro"], "mobileapps": ["applis mobiles", "mobile apps"], "music_instrumental": ["musique instrumentale", "instrumental music"], "music_vocals": ["musique chantée", "vocal music"], "overall": ["global", "overall"], "rerank": ["qualité", "quality"], "rerank_speed": ["vitesse", "speed"], "retrieval_fr": ["recherche en français", "French retrieval"], "scicode": ["SciCode", "SciCode"], "speech_to_speech": ["conversation vocale", "speech to speech"], "speed": ["vitesse", "speed"], "svg": ["SVG", "SVG"], "text": ["texte", "text"], "text_coding": ["code", "coding"], "text_creative": ["écriture créative", "creative writing"], "text_french": ["texte en français", "French text"], "text_to_image": ["image", "text to image"], "text_to_video": ["vidéo depuis texte", "text to video"], "trustworthiness": ["fiabilité", "trustworthiness"], "tts": ["voix", "text to speech"], "uicomponent": ["composants d'interface", "UI components"], "video_edit": ["édition vidéo", "video editing"], "vision": ["vision", "vision"], "webdev": ["développement web", "web development"], "website": ["sites web", "websites"], "wer": ["taux d'erreur (WER)", "word error rate"]} | bench_task -> (fr, en) |
| interface/page.py | `TABS` | [["home", "🏠", "Vue d'ensemble"], ["chat", "💬", "Texte"], ["image", "🖼️", "Image"], ["video", "🎬", "Vidéo"], ["audio", "🎧", "Audio & musique"], ["memory", "🔎", "Mémoire & recherche"], ["decisions", "🧭", "Décision"], ["subs", "💳", "Abonnements"]] |  |
| interface/page.py | `TAB_OF` | {"audio": "audio", "chat": "chat", "decisions": "decisions", "embedding": "memory", "image": "image", "music": "audio", "rerank": "memory", "transcription": "audio", "video": "video"} |  |
| interface/page.py | `LEVELS` | {"L1": ["Économique", "Quotidien : réponses courtes, résumés, petites rédactions"], "L2": ["Intermédiaire", "Analyse en plusieurs étapes, comparaison, rédaction soignée"], "L3": ["Haut de gamme", "Raisonnement profond, synthèse, enjeu important"]} |  |
| interface/page.py | `EFFORT` | {"high": "élevée", "low": "faible", "max": "maximale", "medium": "moyenne", "xhigh": "très élevée"} |  |
| interface/page.py | `ORIGIN` | {"calcul": "Calculé", "méthode des niveaux": "Méthode Pareto", "toi": "Ton choix"} |  |
| interface/page.py | `ORIGIN_ICON` | {"email": "📧 mail", "measure": "📏 mesure", "owner": "✍️ toi", "web": "🌐 web"} |  |
| interface/page.py | `METRIC_FR` | {"limit_note": "limite", "messages_5h": "messages par 5 h", "messages_week": "messages par semaine", "plan_change": "événement", "price_usd_month": "prix par mois", "tokens_month": "tokens par mois", "usd_value_month": "valeur API par mois"} |  |
| interface/page.py | `EXCLUDED` | {"not included in Pro (usage credits at API price)": "non inclus dans Pro (crédits payés au prix API)"} |  |
| interface/translate.py | `PHRASES` | {" % de lectures en cache ; tokens par mois = valeur ÷ prix moyen du million sur ce mélange.": " % cache reads; tokens per month = value ÷ average price per million on that mix.", " : valeur du forfait entièrement utilisé, sur un usage agentique de ": ": value of the plan fully used, on an agentic workload with ", " ; cycle complet automatique toutes les 48 heures, page republiée après chacune de tes réponses.": "; full cycle every 48 hours, page republished after each of your answers.", " Md": " B", " points de compteur": " meter points", " · puis ": " · then ", "$/img estimé": "$/img estimated", "$/recherche": "$/search", "$/requête": "$/request", "(abonnement)": "(subscription)", "(gratuit)": "(free)", "(même modèle)": "(same model)", "(pas de fournisseur branché)": "(no provider wired)", "(proposé par aucun de nos fournisseurs)": "(offered by none of our providers)", "(si payant)": "(if paid)", ", échelle logarithmique": ", log scale", "7 jours glissants": "rolling 7 days", "AA ne teste pas encore la vision : classé sur l'index texte, parmi ceux qui lisent les images": "AA does not test vision yet: ranked on the text index, among models that read images", "Abonnement": "Subscription", "Abonnements": "Subscriptions", "Abonnements indisponibles : ": "Subscriptions unavailable: ", "Abscisse : ": "X axis: ", "Aide texte pendant un appel vocal": "Text helper during a phone call", "Analyse d'image": "Image analysis", "Analyse de document / PDF": "Document / PDF analysis", "Analyse en plusieurs étapes, comparaison, rédaction soignée": "Multi-step analysis, comparison, careful writing", "Animer une image": "Animate an image", "Application full-stack (agent)": "Full-stack app (agent)", "Application mobile (agent)": "Mobile app (agent)", "Arena retouche d'image": "Arena image editing", "Aucun modèle": "No model", "Audio & musique": "Audio & music", "Bibliothèque des modèles": "Model library", "Bibliothèque des modèles — Walter Router": "Model library — Walter Router", "Budget / brouillon": "Budget / draft", "Calcul": "Calculation", "Calculé": "Computed", "Capacité du forfait utilisé à 100 %": "Plan capacity at 100 % use", "Ce que tes forfaits valent au prix API : notre mesure sur ton compte et les chiffres publiés par SemiAnalysis. Information seulement, le routage ne change pas.": "What your plans are worth at API prices: our measurement on your account and the figures published by SemiAnalysis. Information only, routing is unchanged.", "Classement inaccessible : ": "Leaderboard unreachable: ", "Classements recalculés le ": "Leaderboards recomputed on ", "Code / back-end / agentique": "Code / back-end / agentic", "Codex (abonnement) inclus": "Codex (subscription) included", "Codex (secours)": "Codex (fallback)", "Composant d'interface": "UI component", "Compteur Claude estimé = entrée + écriture en cache + 5 × sortie, lectures en cache gratuites, sur une capacité tirée de SemiAnalysis tant qu’il n’est pas calibré. ": "Estimated Claude meter = input + cache writes + 5 × output, cache reads free, over a capacity taken from SemiAnalysis until it is calibrated. ", "Compteur et consommation des 7 derniers jours": "Meter and usage over the last 7 days", "Compteur hebdo": "Weekly meter", "Conversation vocale temps réel": "Real-time voice conversation", "Coût AA officiel": "Official AA cost", "Coût du million": "Cost per million", "Coût du million à ton rythme": "Cost per million at your pace", "Coût du million à ton rythme = prix de la semaine ÷ tokens de la semaine. ": "Cost per million at your pace = the week’s price ÷ the week’s tokens. ", "Coût réel": "Real cost", "Cybersécurité": "Cybersecurity", "Décision": "Decision", "Extraction mémoire structurée": "Structured memory extraction", "Finance / comptabilité / économie": "Finance / accounting / economics", "Flow à la main": "Flow, by hand", "Forfait entier": "Whole plan", "Fournisseurs": "Providers", "Fournisseurs (ordre, prix)": "Providers (order, price)", "Frontière de Pareto": "Pareto frontier", "Gemini AI Pro (crédits Flow)": "Gemini AI Pro (Flow credits)", "Graphisme / affiche": "Graphic design / poster", "Haut de gamme": "High end", "Indice AA": "AA index", "Indice AA en fonction du coût réel par tâche": "AA index vs real cost per task", "Ingénierie": "Engineering", "Intermédiaire": "Intermediate", "Jeu (canvas / HTML5)": "Game (canvas / HTML5)", "Juridique / droit": "Legal", "Kie (payant)": "Kie (paid)", "Le router conserve sa dernière lecture valable pendant 21 jours.": "The router keeps its last valid reading for 21 days.", "Logo / identité visuelle": "Logo / visual identity", "Long contexte (très longs documents)": "Long context (very long documents)", "Lus en cache": "Cache reads", "Mes choix ≠ n°1": "My picks ≠ #1", "Modèle": "Model", "Modèle de décision (routage d'intention, tri)": "Decision model (intent routing, triage)", "Modèle de décision avec image (navigation, traitement d'images en masse)": "Decision model with images (browsing, bulk image processing)", "Modèle retenu": "Selected model", "Modèles exécutables": "Runnable models", "Modèles suivis": "Models tracked", "Musique": "Music", "Mémoire & recherche": "Memory & search", "Méthode Pareto": "Pareto method", "Météo": "Weather", "Niveau": "Level", "Niveaux retenus": "Selected levels", "Notre mesure": "Our measurement", "Notre mesure ChatGPT = valeur API consommée entre deux lectures du compteur ÷ points gagnés, ramenée à 100 % (un plancher : l’usage hors de la VM fait monter le compteur sans tokens vus ici). ": "Our ChatGPT measurement = API value used between two meter readings ÷ points gained, scaled to 100 % (a floor: usage outside the VM moves the meter without tokens seen here). ", "N°1 Design Arena, si différent": "Design Arena #1, if different", "Optimum de Pareto calculé par ta méthode sur la frontière AA": "Pareto optimum computed with your method on the AA frontier", "Origine": "Origin", "Origine : « Ton choix » = modèle fixé par toi ; « Calculé » = meilleur modèle exécutable selon les classements\npondérés ; « Méthode Pareto » = niveaux L1, L2, L3. Une ligne surlignée signale un choix de ta part différent du n°1 mesuré, avec la raison.": "Origin: “Your pick” = model you set; “Computed” = best runnable model on the weighted leaderboards; “Pareto method” = levels L1, L2, L3. A highlighted row marks a pick of yours that differs from the measured #1, with the reason.", "Page générée le ": "Page generated on ", "Pas de données AA.": "No AA data.", "Premium / cinématique": "Premium / cinematic", "Prix": "Price", "Prix : texte en dollars par million de tokens (entrée/sortie), image par image, vidéo par seconde (plage selon la résolution) ;\n« estimé » lorsque le fournisseur facture au token.": "Prices: text in dollars per million tokens (input/output), images per image, video per second (range by resolution); “estimated” when the provider bills per token.", "Prix de référence publié par Artificial Analysis": "Reference price published by Artificial Analysis", "Quotidien : réponses courtes, résumés, petites rédactions": "Everyday: short answers, summaries, small writing", "Raisonnement profond, synthèse, enjeu important": "Deep reasoning, synthesis, high stakes", "Rang": "Rank", "Rang du modèle retenu sur le classement Design Arena de chaque tâche": "Rank of the selected model on each task's Design Arena leaderboard", "Recalculé avec le prix du fournisseur utilisé": "Recomputed with the price of the provider in use", "Recherche web": "Web search", "Rechercher": "Search", "Reclassement de résultats (rerank)": "Result reranking", "Remise à zéro": "Resets", "Retouche / édition d'image": "Image retouching / editing", "Rédaction / qualité d'écriture": "Writing quality", "Résumé / compression de contexte": "Summarisation / context compression", "SVG / vectoriel": "SVG / vector", "Santé / médical": "Health / medical", "Sciences / recherche avancée": "Science / advanced research", "Score /100 : moyenne pondérée des classements indiqués sous chaque tâche": "Score /100: weighted average of the leaderboards listed under each task", "Secours": "Fallback", "SemiAnalysis, rapport du ": "SemiAnalysis, report of ", "Site web / landing": "Website / landing page", "Stratégie / conseil / opérations": "Strategy / consulting / operations", "Texte": "Text", "Texte général (niveaux L1/L2/L3)": "General text (levels L1/L2/L3)", "Tokens par mois": "Tokens per month", "Tokens vus sur la VM : Hermes et Codex pour ChatGPT Plus, Claude Code pour Claude Pro. ": "Tokens seen on the VM: Hermes and Codex for ChatGPT Plus, Claude Code for Claude Pro. ", "Ton choix": "Your pick", "Transcription (parole vers texte)": "Transcription (speech to text)", "Tâche": "Task", "Utilisé par": "Used by", "Valeur API": "API value", "Valeur API = tokens réellement consommés, au prix catalogue de l’éditeur. ": "API value = tokens actually used, at the vendor’s list price. ", "Valeur API par mois": "API value per month", "Vectorisation (embeddings)": "Embeddings", "Vidéo": "Video", "Vidéo depuis texte": "Text to video", "Visualisation de données": "Data visualisation", "Voix (lecture)": "Voice (text to speech)", "Vue d'ensemble": "Overview", "aucun modèle exécutable": "no runnable model", "combinaisons modèle × niveau de réflexion exécutables": "runnable model × reasoning-level combinations", "coût officiel par tâche AA (prix de référence)": "official cost per AA task (reference price)", "coût réel par tâche AA (meilleur fournisseur)": "real cost per AA task (best provider)", "du prix API": "of the API price", "en cours : il faut 3 points de compteur dans une même semaine": "in progress: needs 3 meter points within one week", "estimé": "estimated", "estimé, à calibrer": "estimated, to calibrate", "non inclus dans Pro (crédits payés au prix API)": "not included in Pro (credits paid at API price)", "non lu": "not read", "n°1 mesuré : ": "measured #1: ", "par mois": "per month", "pas de fournisseur branché": "no provider wired", "pas encore classée sur ce benchmark": "not ranked on this benchmark yet", "prix de revient": "cost price", "réel": "real", "réflexion faible": "reasoning: low", "réflexion maximale": "reasoning: maximum", "réflexion moyenne": "reasoning: medium", "réflexion très élevée": "reasoning: very high", "réflexion élevée": "reasoning: high", "tâches de fond": "background jobs", "version supérieure de ": "newer version of ", "via Codex (abonnement)": "via Codex (subscription)", "Économique": "Economy", "Édition de vidéo": "Video editing", "Équilibré": "Balanced", "× le prix": "× the price", "à calibrer avec le pourcentage hebdomadaire affiché par claude.ai": "to calibrate with the weekly percentage shown by claude.ai", "— (un seul fournisseur)": "— (single provider)", "▶ Lancer le cycle complet": "▶ Run the full cycle", "🎨 Spécialisations Design Arena": "🎨 Design Arena specialisations", "📈 Indice d'intelligence et coût par tâche": "📈 Intelligence index and cost per task", "🧠 Niveaux de réflexion": "🧠 Reasoning levels"} |  |
| interface/translate.py | `FRENCH_MARKERS` | ["Fournisseur", "Secours", "Abonnement", "Modèle", "Tâche", "réflexion", "Calculé", "mesuré", "Économique", "Vidéo", "Coût", "Rechercher", "Lancer", "généré", "estimé", "Équilibré"] |  |
| interface/translate.py | `JS` | {"' $ par tâche'": "' $ per task'", "' (échec)'": "' (failed)'", "'Enregistré, la page se met à jour…'": "'Saved, the page is updating…'", "'Envoi…'": "'Sending…'", "'Indice '": "'Index '", "'Refusé'": "'Refused'", "'Résilier ce plan ? Il sortira de tes abonnements (gardé dans l’historique).'": "'Cancel this plan? It leaves your plans (kept in the history).'", "'démarrage'": "'starting'", "'fr-FR'": "'en-GB'", "'Échec de l’envoi'": "'Sending failed'", "Cycle en cours — ": "Cycle running — ", "Dernier cycle complet : ": "Last full cycle: ", "Lancement…": "Starting…", "Lancer maintenant le cycle complet ? Collecte des classements, recalcul, analyse par le modèle économique, notifications et republication de cette page (20 à 60 minutes).": "Run the full cycle now? Leaderboard collection, recomputation, analysis by the economy model, notifications and republication of this page (20 to 60 minutes).", "Statut indisponible": "Status unavailable", "Échec du lancement": "Launch failed"} |  |
| interface/translate.py | `STEPS` | {"1/4 recherche et analyse": "1/4 research and analysis", "2/4 agent de recherche (modèle économique)": "2/4 research agent (economy model)", "3/4 analyse finale et notifications": "3/4 final analysis and notifications", "4/4 Hermes et page": "4/4 Hermes and page"} |  |
| interface/translate.py | `BOARD_TASKS_EN` | {"animation d'image": "image animation", "embeddings latence": "embeddings latency", "fidélité (100 − WER)": "accuracy (100 − WER)", "musique": "music", "recherche en français": "French retrieval", "rerank latence": "rerank latency", "retouche d'image": "image editing", "texte": "text", "vidéo depuis texte": "text to video", "vitesse": "speed", "voix": "voice"} |  |
| interface/translate.py | `_SOURCES` | ["AA", "AA Decision", "AA STT", "Design Arena", "Arena", "BridgeBench", "Agentset", "MTEB"] |  |
| llm/antigravity_subscription.py | `PROVIDER` | antigravity |  |
| llm/antigravity_subscription.py | `DENY_ALL` | {"permissions": {"deny": ["read_file(*)", "write_file(*)", "read_url(*)", "execute_url(*)", "command(*)", "mcp(*)", "unsandboxed(*)"]}} |  |
| llm/antigravity_subscription.py | `EFFORTS` | ["low", "medium", "high"] |  |
| llm/antigravity_subscription.py | `EFFORT_OF` | {"high": "high", "low": "low", "max": "high", "medium": "medium", "minimal": "low", "non-reasoning": "low", "none": "low", "xhigh": "high"} |  |
| llm/antigravity_subscription.py | `NO_TOOLS` | Answer directly in text from your own knowledge. You have no tools: do not try to read or write files, run commands or open pages. |  |
| llm/claude_subscription.py | `PROVIDER` | claude-pro |  |
| llm/claude_subscription.py | `GRANT` | claude-subscription |  |
| llm/claude_subscription.py | `UPSTREAM` | https://api.anthropic.com/v1/messages |  |
| llm/gateway.py | `ROUTER` | walter-router | Walter Router CLI on the PATH |
| llm/gateway.py | `UA` | Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36 |  |
| llm/gateway.py | `DEFAULT_TASK` | coding |  |
| llm/gateway.py | `CODEX_GRANT` | codex-subscription |  |
| llm/gateway.py | `KEY_TTL` | 600 |  |
| llm/gateway.py | `ROUTE_TTL` | 600 |  |
| llm/gateway.py | `KIE_GPT` | ["gpt-"] |  |
| llm/gateway.py | `PAID` | ["arnict", "kie", "openrouter", "venice"] | providers billed per call (subscriptions are not) |
| llm/gateway.py | `RATE_LIMIT_WAITS` | [4, 12] |  |
| llm/gateway.py | `EXACT` | exact: | a model named by the owner, validated by Walter Router (lot E5) |
| llm/gateway.py | `ANTHROPIC_CACHE_POINTS` | [{"location": "message", "role": "system"}, {"index": -1, "location": "message"}] |  |
| llm/gateway.py | `QUOTA_SWITCH` | 90.0 | same threshold as the Router's execution.routes (weekly %), mirrored for the trace only |
| plan/codex_account.py | `BASE` | https://chatgpt.com/backend-api |  |
| plan/codex_account.py | `GRANT` | codex-subscription |  |
| plan/codex_account.py | `CLIENT_VERSIONS` | ["99.0.0", "0.0.0"] |  |
| plan/codex_account.py | `WINDOW_BY_SECONDS` | {"18000": "session", "604800": "weekly"} |  |
| plan/codex_account.py | `WINDOW_BY_POSITION` | [["primary_window", "session"], ["secondary_window", "weekly"]] |  |
| plan/mail.py | `API` | https://gmail.googleapis.com/gmail/v1/users/me |  |
| plan/mail.py | `GRANT` | google-memory |  |
| plan/mail.py | `VENDORS` | {"anthropic.com": "Anthropic", "cursor.com": "Cursor", "elevenlabs.io": "ElevenLabs", "google.com": "Google", "kie.ai": "Kie", "midjourney.com": "Midjourney", "mistral.ai": "Mistral", "openai.com": "OpenAI", "openrouter.ai": "OpenRouter", "perplexity.ai": "Perplexity", "runwayml.com": "Runway", "suno.com": "Suno", "x.ai": "xAI"} |  |
| plan/mail.py | `WORDS` | (receipt OR invoice OR reçu OR facture OR subscription OR abonnement OR renewal OR renouvellement OR upgrade OR cancel OR annulation OR welcome OR bienvenue OR essai OR trial OR "your plan" OR "votre forfait") |  |
| plan/mail.py | `PRODUCT` | {"Anthropic": "Claude", "Google": "Google AI", "OpenAI": "ChatGPT", "xAI": "SuperGrok"} |  |
| plan/mail.py | `PAY_AS_YOU_GO` | ["Kie", "OpenRouter"] | credit top-ups, not plans |
| plan/mail.py | `GOOGLE_BILLING` | ["googleplay-noreply@google.com", "payments-noreply@google.com", "googleone-noreply@google.com"] |  |
| plan/news.py | `SENDERS` | {"Anthropic": ["anthropic.com"], "Google": ["googleone-noreply@google.com", "gemini-noreply@google.com"], "Mistral": ["mistral.ai"], "OpenAI": ["openai.com"], "Perplexity": ["perplexity.ai"], "xAI": ["x.ai"]} |  |
| plan/news.py | `NEWS_DAYS` | 21 |  |
| plan/quota_watch.py | `SOURCE_SUBS` | {"claude_code": "anthropic-pro", "codex": "openai-plus", "hermes": "openai-plus"} |  |
| plan/quota_watch.py | `MIN_AGE_S` | {"anthropic-pro": 300, "openai-plus": 120} |  |
| plan/subscriptions.py | `KINDS` | ["input", "cache_read", "cache_write", "cache_write_1h", "output"] |  |
| plan/subscriptions.py | `MIN_POINTS` | 3 | meter points between two readings before we trust a capacity (Codex reports whole percents) |
| plan/watch.py | `METRICS` | ["usd_value_month", "tokens_month", "messages_5h", "messages_week", "price_usd_month", "limit_note"] |  |
| plan/watch.py | `PROMPT` | Tu fais la veille des abonnements IA de {owner}. Ses plans actuels (JSON) :<br>{plans}<br><br>Faits déjà connus (ne les redonne pas sauf s'ils ont changé) :<br>{known}<br><br>Cherche sur le web (au plus 10 recherches, pages officielles d'abord : aide, tarifs, notes de version de l'éditeur ;<br>puis analyses sérieuses et datées : SemiAnalysis / Tokenomics, autres mesures publiées de la valeur d'un plan au prix<br>de l'API ou du nombre de tokens / messages par fenêtre). Pour CHAQUE plan : prix actuel, limites publiées (fenêtre de<br>5 h, hebdomadaire, modèles inclus), valeur mensuelle au prix API par modèle si quelqu'un l'a mesurée.<br><br>Réponds UNIQUEMENT par un tableau JSON, sans texte autour. Chaque élément :<br>{{"sub_id": "<id du plan ou null>", "vendor": "...", "plan": "...", "model_id": "<id router du modèle ou null>",<br>  "metric": "usd_value_month \| tokens_month \| messages_5h \| messages_week \| price_usd_month \| limit_note",<br>  "value": <nombre ou null>, "unit": "...", "source_name": "...", "source_url": "https://...",<br>  "published": "AAAA-MM-JJ ou null", "quote": "<phrase exacte de la source, 300 caractères max>"}}<br>N'invente rien : un fait sans URL vérifiée n'est pas rendu. Tableau vide si rien de nouveau. |  |
| research/agent/review.py | `MY_PROVIDERS` | ["openrouter", "kie", "codex", "arnict", "google-flow"] |  |
| research/benchmarks/aa.py | `AA_MODEL_URL` | https://artificialanalysis.ai/models/{} |  |
| research/benchmarks/aa.py | `ANCHORS` | ["gpt-6-luna", "gpt-5-6-luna", "claude-opus-5-5", "deepseek-v4-pro"] |  |
| research/benchmarks/aa.py | `AA_LEADERBOARD_URL` | https://artificialanalysis.ai/leaderboards/models |  |
| research/benchmarks/aa.py | `AA_API_URL` | https://artificialanalysis.ai/api/v2/data/llms/models |  |
| research/benchmarks/aa.py | `AA_METHODOLOGY_URL` | https://artificialanalysis.ai/methodology/intelligence-benchmarking |  |
| research/benchmarks/aa.py | `MIN_PRICED` | 40 |  |
| research/benchmarks/aa.py | `MAX_DISAGREEMENT` | 0.25 |  |
| research/benchmarks/aa.py | `SCORE_TOLERANCE` | 0.05 |  |
| research/benchmarks/aa.py | `AA_INDEXES_URL` | https://artificialanalysis.ai/indexes |  |
| research/benchmarks/aa_decision.py | `AA_DECISION_URL` | https://artificialanalysis.ai/evaluations/artificial-analysis-decision-index |  |
| research/benchmarks/aa_evaluations.py | `EVAL_URL` | https://artificialanalysis.ai/evaluations/{} |  |
| research/benchmarks/aa_evaluations.py | `INDEX_URL` | https://artificialanalysis.ai/indexes/{} |  |
| research/benchmarks/aa_evaluations.py | `INDEXES` | {"idx_economics": "economics", "idx_engineering": "engineering", "idx_finance": "finance-and-accounting", "idx_legal": "legal", "idx_medical": "healthcare-and-medical", "idx_strategy_ops": "strategy-and-ops"} |  |
| research/benchmarks/aa_evaluations.py | `PAGE_ONLY` | ["healthbench", "healthbench_pro", "cyber"] |  |
| research/benchmarks/aa_evaluations.py | `MIN_MODELS` | 300 |  |
| research/benchmarks/aa_stt.py | `AA_STT_URL` | https://artificialanalysis.ai/speech-to-text |  |
| research/benchmarks/aa_stt.py | `AA_STT_TABLES` | ["STT AA-WER vs Price", "STT AA-WER vs Speed Factor", "STT Speed Factor vs Price"] |  |
| research/benchmarks/agentset.py | `AGENTSET_URLS` | {"embeddings": "https://agentset.ai/embeddings", "rerank": "https://agentset.ai/rerankers"} |  |
| research/benchmarks/arena.py | `ARENA_URL` | https://arena.ai/leaderboard/ |  |
| research/benchmarks/arena.py | `ARENA_BOARDS` | {"agent": "agent", "chat/document": "document", "chat/search": "search", "chat/text": "text", "chat/text/coding": "text_coding", "chat/text/creative-writing": "text_creative", "chat/vision": "vision", "code/image-to-webdev": "image_to_webdev", "code/webdev": "webdev", "image/image-edit/single-image": "image_edit", "image/text-to-image": "text_to_image", "text/french": "text_french", "video/image-to-video": "image_to_video", "video/text-to-video": "text_to_video", "video/video-edit": "video_edit"} |  |
| research/benchmarks/arena.py | `BOARD_NAMES` | {"document": "document-overall-raw", "image_edit": "image_edit-overall-raw", "image_to_video": "image_to_video-overall-raw", "image_to_webdev": "image_to_webdev-overall-raw", "search": "search-overall-raw", "text": "text-overall-style_control", "text_coding": "text-coding-style_control", "text_creative": "text-creative_writing-style_control", "text_french": "text-french-style_control", "text_to_image": "text_to_image-overall-raw", "text_to_video": "text_to_video-overall-raw", "video_edit": "video_to_video-overall-raw", "vision": "vision-overall-style_control", "webdev": "webdev-overall-raw"} |  |
| research/benchmarks/arena.py | `BROWSER_TIMEOUT` | 90 | one public page, including navigation and bounded CLI reads |
| research/benchmarks/arena.py | `BROWSER_BUDGET` | 600 | shared across the collection; no per-board timeout multiplication without a ceiling |
| research/benchmarks/bridgebench.py | `BRIDGEBENCH_URL` | https://www.bridgebench.ai/leaderboard |  |
| research/benchmarks/design_arena.py | `DA_BASE` | https://www.designarena.ai |  |
| research/benchmarks/design_arena.py | `CATEGORIES` | ["allcategories", "website", "uicomponent", "gamedev", "dataviz", "3d", "svg", "graphicdesign", "logo"] |  |
| research/benchmarks/design_arena.py | `AGENT_CATEGORIES` | ["fullstack", "agon_webapps", "mobileapps", "nativeapps", "agentic_3d", "agon_dataviz", "agon_html"] |  |
| research/benchmarks/design_arena.py | `PAUSE_S` | 0.5 | crowdsourced API: one call at a time |
| research/benchmarks/mteb.py | `MTEB_API` | https://api.github.com/repos/embeddings-benchmark/results/contents/results |  |
| research/benchmarks/mteb.py | `MTEB_RAW` | https://raw.githubusercontent.com/embeddings-benchmark/results/main/results |  |
| research/benchmarks/mteb.py | `MTEB_FR` | {"retrieval_fr": ["MIRACLRetrievalHardNegatives", "fr"]} |  |
| research/benchmarks/mteb.py | `OPENROUTER_EMBEDDINGS_URL` | https://openrouter.ai/api/v1/models?output_modalities=embeddings |  |
| research/categories/__init__.py | `NAMES` | ["text", "image", "video", "audio", "memory", "decision", "prices", "hosts", "plans"] |  |
| research/categories/audio.py | `LABEL` | ["Audio et musique", "Audio and music"] |  |
| research/categories/audio.py | `ICON` | 🎧 |  |
| research/categories/audio.py | `SOURCES` | {"aa_stt": null, "mm": ["music", "speech_to_speech", "tts"]} |  |
| research/categories/decision.py | `LABEL` | ["Décision", "Decision"] |  |
| research/categories/decision.py | `ICON` | 🧭 |  |
| research/categories/decision.py | `SOURCES` | {"aa_decision": null} |  |
| research/categories/hosts.py | `LABEL` | ["Hébergeurs", "Hosts"] |  |
| research/categories/hosts.py | `ICON` | 🏷️ |  |
| research/categories/hosts.py | `SOURCES` | {"or_endpoints": null} |  |
| research/categories/image.py | `LABEL` | ["Image", "Image"] |  |
| research/categories/image.py | `ICON` | 🖼️ |  |
| research/categories/image.py | `SOURCES` | {"arena": ["image_edit", "text_to_image"], "da": ["graphicdesign", "logo"], "mm": ["image"]} |  |
| research/categories/memory.py | `LABEL` | ["Mémoire et recherche", "Memory and search"] |  |
| research/categories/memory.py | `ICON` | 🔎 |  |
| research/categories/memory.py | `SOURCES` | {"agentset": null, "mteb": null} |  |
| research/categories/plans.py | `LABEL` | ["Abonnements", "Subscriptions"] |  |
| research/categories/plans.py | `ICON` | 💳 |  |
| research/categories/plans.py | `SOURCES` | {} |  |
| research/categories/plans.py | `EXTRA` | subscriptions | not a snapshot source: the plan module (walter_router.plan) runs: meters, mails, web, news, cost price |
| research/categories/prices.py | `LABEL` | ["Prix des fournisseurs", "Provider prices"] |  |
| research/categories/prices.py | `ICON` | 💲 |  |
| research/categories/prices.py | `SOURCES` | {"codex": null, "declared": null, "hermes_providers": null, "kie": null, "openrouter": null} |  |
| research/categories/text.py | `LABEL` | ["Texte et spécialités", "Text and specialised domains"] |  |
| research/categories/text.py | `ICON` | 📝 |  |
| research/categories/text.py | `SOURCES` | {"aa": null, "aa_eval": null, "arena": ["agent", "document", "image_to_webdev", "search", "text", "text_coding", "text_creative", "text_french", "vision", "webdev"], "bridgebench": null, "da": ["3d", "agents", "allcategories", "dataviz", "gamedev", "svg", "uicomponent", "website"]} |  |
| research/categories/video.py | `LABEL` | ["Vidéo", "Video"] |  |
| research/categories/video.py | `ICON` | 🎬 |  |
| research/categories/video.py | `SOURCES` | {"arena": ["image_to_video", "text_to_video", "video_edit"], "mm": ["video"]} |  |
| research/prices/kie.py | `KIE_URL` | https://api.kie.ai/client/v1/model-pricing/page |  |
| research/prices/openrouter.py | `MEDIA_INTERFACES` | ["image", "video", "audio", "music"] |  |
| research/prices/openrouter.py | `_OR_OUTPUTS` | {"audio": "audio", "embeddings": "embedding", "image": "image", "rerank": "rerank", "speech": "audio", "transcription": "transcription", "video": "video"} |  |
| research/prices/openrouter.py | `OPENROUTER_URL` | https://openrouter.ai/api/v1/models?output_modalities=all |  |
| research/prices/openrouter_endpoints.py | `ENDPOINTS_URL` | https://openrouter.ai/api/v1/models/{}/endpoints |  |
| research/prices/openrouter_endpoints.py | `PAUSE_S` | 0.15 |  |
| research/sources.py | `PARTIAL` | {"arena": "boards", "da": "categories", "mm": "modules"} |  |
| serve/agent_view.py | `KEEP` | ["task", "mode", "role", "role_label", "matched_signals", "model_id", "variant", "display_name", "provider", "level", "objective", "quality", "quality_unit", "real_cost", "cost_unit", "why", "warning", "require", "score_from_base", "unrestricted_signals", "role_source"] |  |
| serve/brief.py | `MAX_CHARS` | 4000 |  |
| serve/brief.py | `ANALYSIS` | ["vision", "document", "long_context"] | chat tasks that read what they are given |
| serve/brief.py | `LEVELS_FR` | {"L1": "quotidien : réponse courte, résumé simple, fait rapide, petite reformulation", "L2": "plus dur : analyse en plusieurs étapes, comparaison, rédaction soignée, planification", "L3": "le plus dur ou à fort enjeu : recherche approfondie, raisonnement complexe, décision importante"} |  |
| serve/brief.py | `CONSTRAINTS_FR` | {"open_weights": "modèle à poids ouverts", "unrestricted": "contenu que les modèles grand public refusent", "video_input": "le modèle lit une vidéo (avec task=vision : analyser ou revoir une vidéo)"} |  |
| serve/brief.py | `GENERATION` | [["Images", ["image"]], ["Vidéo", ["video"]], ["Audio", ["audio", "music"]]] |  |
| serve/choose.py | `LEVELS` | ["L1", "L2", "L3"] |  |
| serve/choose.py | `POLICY` | coalesce(pr.content_policy, c.content_policy) |  |
| serve/choose.py | `INPUTS` | {"video_input": ["video"]} | requirement -> inputs every route of the choice must read |
| serve/engine.py | `ENGINE_TASKS` | ["coding", "general", "document", "summarization"] | engine models = walter-llm postes |
| serve/engine.py | `TASK_OF` | {"code": "coding", "front": "coding"} | router task → engine poste when names differ |
| serve/execution.py | `HERMES_PROVIDERS` | {"arnict": "arnict", "codex": "openai-codex", "kie": "kie", "openrouter": "openrouter"} |  |
| serve/execution.py | `NATIVE_ONLY` | ["antigravity", "venice"] | providers walter-llm runs itself (2026-10-30), with no Hermes provider |
| serve/execution.py | `KIE_CODEX_MODELS` | ["gpt-5-5", "gpt-5-6-luna", "gpt-5-6-sol", "gpt-5-6-terra", "gpt-6-1-sol", "gpt-6-astra", "gpt-6-luna", "gpt-6-sol"] |  |
| serve/execution.py | `MIN_CREDIT_USD` | 1.0 | below this, OpenRouter routes go last (a 402 after minutes of agent work is worse) |
| serve/execution.py | `SLOW_MS` | 30000 | a 5-token probe slower than this = degraded (Kie Claude took 64 s on 2026-10-02) |
| serve/execution.py | `REASONING` | {"high": "high", "low": "low", "max": "max", "medium": "medium", "minimal": "minimal", "non-reasoning": "none", "xhigh": "xhigh"} |  |
| serve/execution.py | `UA` | Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36 |  |
| serve/execution.py | `PROVIDER_RANK` | {"arnict": 1, "kie": 1, "kie-codex": 1, "openrouter": 3} |  |
| serve/execution.py | `KIE_MAX_PREMIUM` | 1.25 |  |
| serve/execution.py | `UNRELIABLE_MIN_RUNS` | 3 |  |
| serve/execution.py | `UNRELIABLE_FAIL_RATE` | 0.5 |  |
| serve/execution.py | `RELIABILITY_DAYS` | 14 |  |
| serve/execution.py | `QUOTA_SWITCH` | 90.0 | weekly meter %: above it a subscription route goes after the paid ones (quota nearly spent) |
| serve/execution.py | `_TIMEOUT` | 90 |  |
| serve/hermes_sync.py | `AUX_POSTES` | {"compression": "summarization", "curator": "summarization", "title_generation": "summarization", "vision": "vision"} |  |
| serve/hermes_sync.py | `MANAGED` | walter-router | marks the provider_routing.models entries this module writes (others are the owner's) |
| serve/hermes_sync.py | `MAX_FALLBACKS` | 2 |  |
| serve/intent.py | `URL` | https://openrouter.ai/api/alpha/decisions |  |
| serve/intent.py | `MODEL` | ~typesafe/jev-latest |  |
| serve/intent.py | `FREE_FALLBACKS` | ["inception/mercury-decide:free", "cloudflare/clef"] | free: survive an exhausted OpenRouter credit |
| serve/intent.py | `ACCEPTED_PREFIXES` | ["typesafe/jev-", "inception/mercury-decide", "cloudflare/clef"] |  |
| serve/intent.py | `CF_RUN` | https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/{model} |  |
| serve/intent.py | `MIN_CONFIDENCE` | 0.35 | eval 2026-10-02: a correct task came back at 0.48 |
| serve/intent.py | `LEVELS` | {"L1": "Everyday: short answer, simple summary, quick fact, small rewrite", "L2": "Harder: multi-step analysis, comparison, careful writing, planning", "L3": "Hardest or high stakes: deep research synthesis, complex reasoning, important decision"} |  |
| serve/intent.py | `UNRESTRICTED` | {"no": "Standard content any mainstream model accepts", "yes": "Needs an uncensored model: explicit adult content or content mainstream models refuse"} |  |
| serve/intent.py | `VIDEO_TASKS` | ["text_to_video", "image_to_video"] |  |
| serve/media_exec.py | `KIE` | https://api.kie.ai |  |
| serve/media_exec.py | `OPENROUTER` | https://openrouter.ai/api/v1 |  |
| serve/media_exec.py | `KIE_USD_PER_CREDIT` | 0.005 | 6 credits = 0.03 $ (Sunburst 1K, 2026-10-02) |
| serve/media_exec.py | `TIMEOUTS` | {"audio": 300, "image": 360, "music": 600, "video": 1200} |  |
| serve/media_exec.py | `FALLBACK_COST_X` | 2.0 |  |
| serve/named.py | `PROVIDERS` | {"arnict": "arnict", "chatgpt": "codex", "codex": "codex", "flow": "google-flow", "google-flow": "google-flow", "kie": "kie", "kie-codex": "kie", "kie.ai": "kie", "openai-codex": "codex", "openrouter": "openrouter", "venice": "venice"} |  |
| serve/named.py | `DEFAULT_TASK` | {"audio": "tts", "chat": "general", "image": "text_to_image", "music": "music", "video": "text_to_video"} |  |
| serve/oneshot.py | `TOKEN_FILE` | @instance/bootstrap/llm/walter-router.env |  |
| serve/oneshot.py | `ECONOMIC` | general/L1 |  |
| serve/run.py | `ALLOWED_TOOLSETS` | ["web", "walter-web", "file", "terminal", "vision", "skills", "code_execution", "memory"] |  |
| serve/run.py | `DEFAULT_TOOLSETS` | ["walter-web", "skills", "memory"] |  |
| serve/run.py | `TOOLSET_TOOLS` | {"memory": ["memory_context", "memory_search", "memory_events"], "skills": ["skills_search", "skill_read"], "walter-web": ["walter_browse"], "web": ["walter_browse"]} |  |
| serve/run.py | `TOOL_FAMILY_TOOLSETS` | {"research": ["walter-web", "skills"], "weather": ["walter-web"]} | mode "tool" tasks |
| serve/run.py | `MEDIA` | ["image", "video", "music", "audio"] |  |
| serve/text_agent.py | `DISABLED_TOOLSETS` | {"code_execution": "no_sandbox", "terminal": "no_sandbox"} |  |
| serve/web.py | `DEFAULT_CONVERSATION` | walter-router |  |
| serve/web.py | `MAX_FILES` | 10 |  |
| serve/web.py | `KEYS` | ["service", "message", "model", "files", "conversation", "request_id", "timeout_s"] |  |

## Variables d’environnement lues ou initialisées

| Variable | Source | Accès | Défaut (expression de code) | Effet |
|---|---|---|---|---|
| `WALTER_ROUTER_CLI` | hermes-plugins/walter-router/__init__.py | get | 'walter-router' | Commande publique appelée par l'adaptateur de tools. |
| `WALTER_LLM_URL` | hermes-plugins/walter-router/__init__.py | get | 'http://127.0.0.1:8894' | URL loopback de la passerelle walter-llm pour les commandes Telegram des services web conversationnels (défaut http://127.0.0.1:8894). |
| `TELEGRAM_HOME_CHANNEL` | hermes-plugins/walter-router/__init__.py | get | aucun | Destination d'instance des avis/propositions ; ne pas exporter sa valeur. |
| `WALTER_LLM_TOKEN` | hermes-plugins/walter-router/__init__.py | get | '' | Jeton local d'agent de Hermes pour la passerelle walter-llm (~/.hermes/.env, jamais affiché). |
| `HERMES_HOME` | hermes-plugins/walter-router/__init__.py | get | aucun | Emplacement du runtime historique pour les opérations/adaptateurs qui en dépendent encore. |
| `HERMES_HOME` | instance.py | get | aucun | Emplacement du runtime historique pour les opérations/adaptateurs qui en dépendent encore. |
| `CHATGPT_TOKEN_DIR` | llm/gateway.py | setdefault | str(CHATGPT_DIR) | Réglage du transport de l'abonnement ; l'authentification reste fournie par son grant. |
| `CHATGPT_DEFAULT_INSTRUCTIONS` | llm/gateway.py | setdefault | "You are a precise assistant for W.Alter's background jobs. Follow the system and user instructions exactly; answer in the language of the request." | Instructions de base du transport d'abonnement, indépendantes du goal de la sous-tâche. |
| `WALTER_RUN_CHANNEL` | llm/gateway.py | get | aucun | test = run d'essai (posé par walter-scenario / walter-lab) : dépense payante plafonnée par walter-llm (test_budget), au-delà validation du propriétaire. |
| `WALTER_LLM_PORT` | llm/gateway.py | get | '8894' | Port HTTP loopback de la passerelle (défaut logiciel 8894). |
| `CLAUDE_PROJECTS` | plan/subscriptions.py | get | aucun | Source locale de métriques des sessions Claude pour estimer un abonnement. |
| `CODEX_SESSIONS` | plan/subscriptions.py | get | aucun | Source locale de métriques des sessions Codex pour estimer un abonnement. |
| `WALTER_FLARESOLVERR` | research/web.py | get | 'http://127.0.0.1:8191/v1' | Adresse du service de lecture des sources qui le nécessitent. |
| `WALTER_RUN_ID` | serve/engine.py | get | aucun | Run Walter (runs.runs) servi par l'exécution ; posé par l'adaptateur du harness, inscrit dans models.exec_log. |
| `WALTER_SESSION_ID` | serve/engine.py | get | aucun | Session walter_logs de l'appelant ; parent de la session du sous-agent walter_run. |
| `WALTER_DELEGATION_DEPTH` | serve/engine.py | get | aucun | Profondeur de délégation de l'appelant (0 = le propriétaire) transmise au moteur par une délégation Engine API ; posée par le moteur pour ses sous-tâches. |
| `WALTER_RUN_ID` | serve/execution.py | get | aucun | Run Walter (runs.runs) servi par l'exécution ; posé par l'adaptateur du harness, inscrit dans models.exec_log. |
| `WALTER_TASK_ID` | serve/execution.py | get | aucun | Tâche de sous-agent (runs.tasks) servie par l'exécution walter_run ; inscrite dans models.exec_log. |
| `CLOUDFLARE_ACCOUNT_ID` | serve/intent.py | env_value | aucun | Identifiant du compte pour la voie de décision configurée ; valeur privée hors documentation. |
| `CLOUDFLARE_AI_TOKEN` | serve/intent.py | env_value | aucun | Nom d'un accès secret pour la voie de décision ; ne pas afficher sa valeur. |
| `OPENROUTER_API_KEY` | serve/intent.py | env_value | aucun | Nom d'accès fournisseur ; la passerelle utilise Walter Secrets. |
| `CLOUDFLARE_API_KEY` | serve/intent.py | env_value | aucun | Nom d'un accès secret utilisé par un adaptateur ; ne pas afficher sa valeur. |
| `CLOUDFLARE_EMAIL` | serve/intent.py | env_value | aucun | Identité de compte pour l'adaptateur Cloudflare ; donnée d'instance. |
| `CLOUDFLARE_EMAIL` | serve/intent.py | env_value | aucun | Identité de compte pour l'adaptateur Cloudflare ; donnée d'instance. |
| `CLOUDFLARE_API_KEY` | serve/intent.py | env_value | aucun | Nom d'un accès secret utilisé par un adaptateur ; ne pas afficher sa valeur. |
| `KIE_API_KEY` | serve/media_exec.py | env_value | aucun | Nom d'accès fournisseur ; la passerelle utilise Walter Secrets, pas une clé transmise au modèle. |
| `OPENROUTER_API_KEY` | serve/media_exec.py | env_value | aucun | Nom d'accès fournisseur ; la passerelle utilise Walter Secrets. |
| `OPENROUTER_API_KEY` | serve/media_exec.py | env_value | aucun | Nom d'accès fournisseur ; la passerelle utilise Walter Secrets. |
| `WALTER_LLM_URL` | serve/oneshot.py | get | 'http://127.0.0.1:8894' | URL loopback de la passerelle walter-llm pour les commandes Telegram des services web conversationnels (défaut http://127.0.0.1:8894). |
| `WALTER_LLM_TOKEN` | serve/oneshot.py | get | aucun | Jeton local d'agent de Hermes pour la passerelle walter-llm (~/.hermes/.env, jamais affiché). |
| `WALTER_RUN_ID` | serve/oneshot.py | get | aucun | Run Walter (runs.runs) servi par l'exécution ; posé par l'adaptateur du harness, inscrit dans models.exec_log. |
| `WALTER_RUN_ID` | serve/run.py | get | aucun | Run Walter (runs.runs) servi par l'exécution ; posé par l'adaptateur du harness, inscrit dans models.exec_log. |
| `WALTER_RUN_CONTEXT` | serve/run.py | get | 'walter' | caller = le sous-agent walter_run reçoit seulement le contexte de l'appelant ; sinon le paquet walter-context (context.build scope=child). |
| `WALTER_SESSION_ID` | serve/run.py | get | aucun | Session walter_logs de l'appelant ; parent de la session du sous-agent walter_run. |
| `WALTER_ROUTER_DATABASE_URL` | store/db.py | get | 'postgresql://hindsight@127.0.0.1:5433/hindsight' | DSN PostgreSQL ; secret via .pgpass, jamais dans une URL publiée. |

## Clés des fichiers de configuration livrés

Ces valeurs sont les défauts logiciels, jamais un export des réglages privés de l’instance. Les tableaux sont parcourus avec `[]` ; des clés répétées représentent plusieurs entrées.

| Fichier | Clé | Type | Défaut livré |
|---|---|---|---|
| config/aliases_auto.json | `_doc` | str | Name links added by the 48 h analysis agent (or the owner) through `walter-router alias-add`, each with its evidence. Merged into aliases.json "*" at load. Remove with `walter-router alias-remove <key>`. |
| config/aliases_auto.json | `aliases.gemini-3-1-flash-image.added_at` | str | 2026-10-12T03:40:00+00:00 |
| config/aliases_auto.json | `aliases.gemini-3-1-flash-image.model_id` | str | gemini-3-1-flash-image-gen |
| config/aliases_auto.json | `aliases.gemini-3-1-flash-image.origin` | str | agent |
| config/aliases_auto.json | `aliases.gemini-3-1-flash-image.reason` | str | Google's Gemini API documents gemini-3.1-flash-image as Gemini 3.1 Flash Image; Google's official Gemini notebook describes the same model as image generation/editing. The -gen suffix is descriptive, not a distinct version. https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-image ; https://github.com/GoogleCloudPlatform/generative-ai/blob/main/gemini/getting-started/intro_gemini_3_1_flash_image_gen.ipynb |
| config/aliases_auto.json | `aliases.gpt-3-5-turbo.added_at` | str | 2026-10-04T03:38:46+00:00 |
| config/aliases_auto.json | `aliases.gpt-3-5-turbo.model_id` | str | gpt-35-turbo |
| config/aliases_auto.json | `aliases.gpt-3-5-turbo.origin` | str | agent |
| config/aliases_auto.json | `aliases.gpt-3-5-turbo.reason` | str | Microsoft Azure désigne gpt-35-turbo comme le modèle GPT-3.5 Turbo ; identifiant Azure raccourci du même modèle. https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure |
| config/aliases_auto.json | `aliases.kling-v3-0-pro.added_at` | str | 2026-10-06T03:39:52+00:00 |
| config/aliases_auto.json | `aliases.kling-v3-0-pro.model_id` | str | kling-v3-pro |
| config/aliases_auto.json | `aliases.kling-v3-0-pro.origin` | str | agent |
| config/aliases_auto.json | `aliases.kling-v3-0-pro.reason` | str | Les pages provider décrivent Kling V3.0 Pro et Kling v3 Pro comme le même niveau Pro de la génération V3 ; différence de notation 3.0/V3 uniquement. https://runware.ai/docs/models/klingai-video-3-0-pro.md ; https://www.atlascloud.ai/models/kwaivgi/kling-v3.0-pro/image-to-video |
| config/aliases_auto.json | `aliases.mistral-small-3-1-24b-instruct.added_at` | str | 2026-10-08T03:40:25+00:00 |
| config/aliases_auto.json | `aliases.mistral-small-3-1-24b-instruct.model_id` | str | mistral-small-3-1-24b-instruct-2503 |
| config/aliases_auto.json | `aliases.mistral-small-3-1-24b-instruct.origin` | str | agent |
| config/aliases_auto.json | `aliases.mistral-small-3-1-24b-instruct.reason` | str | La fiche officielle identifie Mistral Small 3.1 v25.03, sorti en mars 2025, et ses variantes base/instruct ; le suffixe 2503 date ce même modèle instruct. https://docs.mistral.ai/models/model-cards/mistral-small-3-1-25-03 |
| config/aliases_auto.json | `aliases.mixtral-8x22b-instruct.added_at` | str | 2026-10-08T03:40:24+00:00 |
| config/aliases_auto.json | `aliases.mixtral-8x22b-instruct.model_id` | str | mistral-8x22b-instruct |
| config/aliases_auto.json | `aliases.mixtral-8x22b-instruct.origin` | str | agent |
| config/aliases_auto.json | `aliases.mixtral-8x22b-instruct.reason` | str | La documentation officielle Mistral identifie le modèle comme Mixtral 8x22B Instruct ; l’ID non classé omet le préfixe Mixtral, il ne s’agit pas d’un autre modèle Mistral 8x22B. https://legal.mistral.ai/ai-governance/models/mixtral-8-22b |
| config/aliases_auto.json | `aliases.qwen-3-8b.added_at` | str | 2026-10-08T03:40:24+00:00 |
| config/aliases_auto.json | `aliases.qwen-3-8b.model_id` | str | qwen-3-8 |
| config/aliases_auto.json | `aliases.qwen-3-8b.origin` | str | agent |
| config/aliases_auto.json | `aliases.qwen-3-8b.reason` | str | La carte officielle Qwen identifie Qwen3-8B (8,2B paramètres) ; l’ID qwen-3-8 omet seulement le suffixe B de la même taille. https://huggingface.co/Qwen/Qwen3-8B |
| config/aliases_auto.json | `aliases.recraft-v4-1.added_at` | str | 2026-10-16T03:46:56+00:00 |
| config/aliases_auto.json | `aliases.recraft-v4-1.model_id` | str | recraftv-4-1 |
| config/aliases_auto.json | `aliases.recraft-v4-1.origin` | str | agent |
| config/aliases_auto.json | `aliases.recraft-v4-1.reason` | str | La documentation officielle de Recraft identifie la famille comme Recraft V4.1 et l’ID API canonique recraftv4_1 ; les deux formes diffèrent seulement par le découpage typographique de recraftv, sans variation de version ni de suffixe de variante. https://www.recraft.ai/docs/api-reference/models/recraft-v4-1 |
| config/aliases_auto.json | `aliases.recraft-v4-1-pro-vector.added_at` | str | 2026-10-04T03:38:52+00:00 |
| config/aliases_auto.json | `aliases.recraft-v4-1-pro-vector.model_id` | str | recraftv-4-1-pro-vector |
| config/aliases_auto.json | `aliases.recraft-v4-1-pro-vector.origin` | str | agent |
| config/aliases_auto.json | `aliases.recraft-v4-1-pro-vector.reason` | str | Les docs officielles Recraft listent un unique modèle Recraft V4.1 Pro Vector ; recraftv est une variante d’écriture compacte, pas une variante de modèle. https://www.recraft.ai/docs/api-reference/getting-started |
| config/aliases_auto.json | `aliases.recraft-v4-pro-vector.added_at` | str | 2026-10-04T03:38:56+00:00 |
| config/aliases_auto.json | `aliases.recraft-v4-pro-vector.model_id` | str | recraftv-4-pro-vector |
| config/aliases_auto.json | `aliases.recraft-v4-pro-vector.origin` | str | agent |
| config/aliases_auto.json | `aliases.recraft-v4-pro-vector.reason` | str | Les docs officielles Recraft listent un unique modèle Recraft V4 Pro Vector ; recraftv est une variante d’écriture compacte, pas une variante de modèle. https://www.recraft.ai/docs/api-reference/getting-started |
| config/aliases_auto.json | `aliases.recraft-v4-vector.added_at` | str | 2026-10-04T03:38:59+00:00 |
| config/aliases_auto.json | `aliases.recraft-v4-vector.model_id` | str | recraftv-4-vector |
| config/aliases_auto.json | `aliases.recraft-v4-vector.origin` | str | agent |
| config/aliases_auto.json | `aliases.recraft-v4-vector.reason` | str | Les docs officielles Recraft listent un unique modèle Recraft V4 Vector ; recraftv est une variante d’écriture compacte, pas une variante de modèle. https://www.recraft.ai/docs/api-reference/getting-started |
| config/aliases_auto.json | `aliases.riverflow-v2-5-pro.added_at` | str | 2026-10-04T03:38:40+00:00 |
| config/aliases_auto.json | `aliases.riverflow-v2-5-pro.model_id` | str | riverflow-2-5-pro |
| config/aliases_auto.json | `aliases.riverflow-v2-5-pro.origin` | str | agent |
| config/aliases_auto.json | `aliases.riverflow-v2-5-pro.reason` | str | Riverflow 2.5 Pro (Sourceful) : le modèle sourceful/riverflow-v2.5-pro est désigné Riverflow 2.5 Pro ; même modèle, seule l’écriture v2.5 varie. https://replicate.com/sourceful/riverflow-v2.5-pro |
| config/aliases_auto.json | `aliases.seedance-1-5-pro.added_at` | str | 2026-10-16T03:46:51+00:00 |
| config/aliases_auto.json | `aliases.seedance-1-5-pro.model_id` | str | seedance-v1-5-pro |
| config/aliases_auto.json | `aliases.seedance-1-5-pro.origin` | str | agent |
| config/aliases_auto.json | `aliases.seedance-1-5-pro.reason` | str | ByteDance présente sous un nom canonique unique « Seedance 1.5 pro » le modèle audio-vidéo concerné ; les identifiants seedance-1-5-pro et seedance-v1-5-pro ne diffèrent que par la notation de la version V1.5. https://seed.bytedance.com/en/seedance1%5F5%5Fpro |
| config/aliases_auto.json | `aliases.seedream-v4.added_at` | str | 2026-10-10T03:40:19+00:00 |
| config/aliases_auto.json | `aliases.seedream-v4.model_id` | str | seedream-4 |
| config/aliases_auto.json | `aliases.seedream-v4.origin` | str | agent |
| config/aliases_auto.json | `aliases.seedream-v4.reason` | str | BytePlus ModelArk identifie le modèle comme Seedream 4.0 (version seedream-4-0-250828) ; seedream-v4 et seedream-4 sont deux écritures de cette même génération. https://docs.byteplus.com/en/docs/ModelArk/1824718 |
| config/declared_offers.json | `_doc` | str | Offers declared by the instance's owner that no provider API lists (web interfaces, subscriptions). Only explicit declarations go here; an instance keeps its own in config/router/declared_offers.json. |
| config/declared_offers.json | `offers` | list | [] |
| config/host.json | `_doc` | str | Host bindings of an instance (shipped default: none). An instance overrides this file in config/router/host.json. Paths: absolute, ~/ or @instance/. log_dir: cycle logs; collect_script: leaderboard collection (empty = skipped); control_env: HMAC secret of the manual trigger; control_origin / library_domain: where the library page and its trigger are served (empty = not published). aa_api_key: vault item and field of the Artificial Analysis Data API key, read through walter-secrets (null = scores from the leaderboard page only). |
| config/host.json | `aa_api_key` | NoneType | — |
| config/host.json | `cloudflare_cli` | str |  |
| config/host.json | `collect_script` | str |  |
| config/host.json | `control_env` | str | @instance/bootstrap/router-control.env |
| config/host.json | `control_origin` | str |  |
| config/host.json | `hermes_profiles_following_router` | list | [] |
| config/host.json | `library_domain` | str |  |
| config/host.json | `log_dir` | str | @instance/logs/router |
| config/host.json | `site_build` | str | @instance/state/router/site |
| config/kie_media_schemas.json | `_doc` | str | Kie market input schemas (docs.kie.ai OpenAPI, fetched 2026-10-02) used to validate/coerce media requests. |
| config/kie_media_schemas.json | `models.ai-music-api/generate._source` | str | request accepted by Kie on 2026-10-02 (Walter test), no public OpenAPI page |
| config/kie_media_schemas.json | `models.ai-music-api/generate.properties.custom_mode.type` | str | boolean |
| config/kie_media_schemas.json | `models.ai-music-api/generate.properties.duration.type` | str | integer |
| config/kie_media_schemas.json | `models.ai-music-api/generate.properties.instrumental.type` | str | boolean |
| config/kie_media_schemas.json | `models.ai-music-api/generate.properties.model.default` | str | V6 |
| config/kie_media_schemas.json | `models.ai-music-api/generate.properties.model.enum[]` | str | V6 |
| config/kie_media_schemas.json | `models.ai-music-api/generate.properties.model.type` | str | string |
| config/kie_media_schemas.json | `models.ai-music-api/generate.properties.negative_tags.type` | str | string |
| config/kie_media_schemas.json | `models.ai-music-api/generate.properties.prompt.type` | str | string |
| config/kie_media_schemas.json | `models.ai-music-api/generate.properties.style.type` | str | string |
| config/kie_media_schemas.json | `models.ai-music-api/generate.properties.title.type` | str | string |
| config/kie_media_schemas.json | `models.ai-music-api/generate.properties.variety.type` | str | integer |
| config/kie_media_schemas.json | `models.ai-music-api/generate.required[]` | str | custom_mode |
| config/kie_media_schemas.json | `models.ai-music-api/generate.required[]` | str | instrumental |
| config/kie_media_schemas.json | `models.ai-music-api/generate.required[]` | str | model |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.aspect_ratio.default` | str | adaptive |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.aspect_ratio.enum[]` | str | 1:1 |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.aspect_ratio.enum[]` | str | 4:3 |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.aspect_ratio.enum[]` | str | 3:4 |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.aspect_ratio.enum[]` | str | 16:9 |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.aspect_ratio.enum[]` | str | 9:16 |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.aspect_ratio.enum[]` | str | 21:9 |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.aspect_ratio.enum[]` | str | adaptive |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.aspect_ratio.type` | str | string |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.duration.default` | int | 5 |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.duration.type` | str | integer |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.first_frame_url.type` | str | string |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.generate_audio.default` | bool | true |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.generate_audio.type` | str | boolean |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.last_frame_url.type` | str | string |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.nsfw_checker.type` | str | boolean |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.output_format.default` | str | mp4 |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.output_format.enum[]` | str | mp4 |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.output_format.enum[]` | str | mov |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.output_format.type` | str | string |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.prompt.type` | str | string |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.reference_audio_urls.type` | str | array |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.reference_image_urls.type` | str | array |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.reference_video_urls.type` | str | array |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.resolution.default` | str | 720p |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.resolution.enum[]` | str | 480p |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.resolution.enum[]` | str | 720p |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.resolution.enum[]` | str | 1080p |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.resolution.type` | str | string |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.return_last_frame.default` | bool | false |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.return_last_frame.type` | str | boolean |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.properties.web_search.type` | str | boolean |
| config/kie_media_schemas.json | `models.bytedance/seedance-2-5.required` | list | [] |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.dialogue_turns.items.speaker_id.type` | str | string |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.dialogue_turns.items.style.type` | str | string |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.dialogue_turns.items.text.type` | str | string |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.dialogue_turns.type` | str | array |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.filler_words.default` | bool | false |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.filler_words.type` | str | boolean |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.speaker_id.type` | str | string |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.default` | str | Fola |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Bodi |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Lumi |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Sadaltager |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Sola |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Sulafat |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Varo |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Zephyr |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Koda |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Kore |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Nika |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Tavi |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Zeno |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Algenib |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Despina |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Erinome |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Kira |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Ludo |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Mako |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Rasalgethi |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Rina |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Alnilam |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Brio |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Jori |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Laomedeia |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Rami |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Veda |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Achird |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Enzo |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Riko |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Sami |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Zali |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Zubenelgenubi |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Algieba |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Aoede |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Autonoe |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Callirrhoe |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Enceladus |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Gero |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Iapetus |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Neno |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Olin |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Tari |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Umbriel |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Achernar |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Charon |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Daro |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Fola |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Hali |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Milo |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Puck |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Arlo |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Cleo |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Fenrir |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Finn |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Leda |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Lora |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Orus |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Enya |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Jett |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Knox |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Nyla |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Sadachbia |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Vindemiatrix |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Cruz |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Elio |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Gacrux |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Pulcherrima |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Schedar |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Tova |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.enum[]` | str | Zuri |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.items.voice_name.type` | str | string |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.speakers.type` | str | array |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.temperature.default` | int | 1 |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.temperature.maximum` | int | 2 |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.temperature.minimum` | int | 0 |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.properties.temperature.type` | str | number |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.required[]` | str | speakers |
| config/kie_media_schemas.json | `models.google/gemini-3-8-flash-tts.required[]` | str | dialogue_turns |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.aspect_ratio.enum[]` | str | 16:9 |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.aspect_ratio.enum[]` | str | 9:16 |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.aspect_ratio.type` | str | string |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.audio_ids.type` | str | array |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.character_ids.type` | str | array |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.duration.enum[]` | str | 4 |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.duration.enum[]` | str | 6 |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.duration.enum[]` | str | 8 |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.duration.enum[]` | str | 10 |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.duration.type` | str | string |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.first_frame_url.type` | str | string |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.image_urls.type` | str | array |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.last_frame_url.type` | str | string |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.prompt.type` | str | string |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.resolution.default` | str | 720p |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.resolution.enum[]` | str | 360p |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.resolution.enum[]` | str | 720p |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.resolution.enum[]` | str | 1080p |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.resolution.enum[]` | str | 4k |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.resolution.type` | str | string |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.seed.type` | str | integer |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.video_list.items.ends.minimum` | int | 0 |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.video_list.items.ends.type` | str | number |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.video_list.items.start.minimum` | int | 0 |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.video_list.items.start.type` | str | number |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.video_list.items.url.type` | str | string |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.properties.video_list.type` | str | array |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.required[]` | str | prompt |
| config/kie_media_schemas.json | `models.google/gemini-omni-flash-1-1.required[]` | str | duration |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.aspect_ratio.enum[]` | str | auto |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.aspect_ratio.enum[]` | str | 1:1 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.aspect_ratio.enum[]` | str | 3:2 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.aspect_ratio.enum[]` | str | 2:3 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.aspect_ratio.enum[]` | str | 4:3 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.aspect_ratio.enum[]` | str | 3:4 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.aspect_ratio.enum[]` | str | 16:9 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.aspect_ratio.enum[]` | str | 9:16 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.aspect_ratio.enum[]` | str | 21:9 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.aspect_ratio.enum[]` | str | 27:16 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.aspect_ratio.enum[]` | str | 16:27 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.aspect_ratio.enum[]` | str | 9:8 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.aspect_ratio.enum[]` | str | 8:9 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.aspect_ratio.type` | str | string |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.background.enum[]` | str | transparent |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.background.enum[]` | str | opaque |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.background.enum[]` | str | auto |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.background.type` | str | string |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.input_urls.type` | str | array |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.prompt.type` | str | string |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.resolution.enum[]` | str | 1K |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.resolution.enum[]` | str | 2K |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.resolution.enum[]` | str | 4K |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.properties.resolution.type` | str | string |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.required[]` | str | prompt |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-image-to-image.required[]` | str | input_urls |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.aspect_ratio.enum[]` | str | auto |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.aspect_ratio.enum[]` | str | 1:1 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.aspect_ratio.enum[]` | str | 3:2 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.aspect_ratio.enum[]` | str | 2:3 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.aspect_ratio.enum[]` | str | 4:3 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.aspect_ratio.enum[]` | str | 3:4 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.aspect_ratio.enum[]` | str | 16:9 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.aspect_ratio.enum[]` | str | 9:16 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.aspect_ratio.enum[]` | str | 21:9 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.aspect_ratio.enum[]` | str | 27:16 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.aspect_ratio.enum[]` | str | 16:27 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.aspect_ratio.enum[]` | str | 9:8 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.aspect_ratio.enum[]` | str | 8:9 |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.aspect_ratio.type` | str | string |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.background.enum[]` | str | transparent |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.background.enum[]` | str | opaque |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.background.enum[]` | str | auto |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.background.type` | str | string |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.prompt.type` | str | string |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.resolution.enum[]` | str | 1K |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.resolution.enum[]` | str | 2K |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.resolution.enum[]` | str | 4K |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.properties.resolution.type` | str | string |
| config/kie_media_schemas.json | `models.gpt-image-2-5-sunburst-text-to-image.required[]` | str | prompt |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.aspect_ratio.default` | str | auto |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.aspect_ratio.enum[]` | str | 1:1 |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.aspect_ratio.enum[]` | str | 16:9 |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.aspect_ratio.enum[]` | str | 9:16 |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.aspect_ratio.enum[]` | str | 3:2 |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.aspect_ratio.enum[]` | str | 2:3 |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.aspect_ratio.enum[]` | str | auto |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.aspect_ratio.type` | str | string |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.duration.default` | int | 8 |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.duration.maximum` | int | 15 |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.duration.minimum` | int | 1 |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.duration.type` | str | integer |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.image_urls.type` | str | array |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.nsfw_checker.type` | str | boolean |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.prompt.type` | str | string |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.resolution.default` | str | 480p |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.resolution.enum[]` | str | 480p |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.resolution.enum[]` | str | 720p |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.resolution.enum[]` | str | 1080p |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.properties.resolution.type` | str | string |
| config/kie_media_schemas.json | `models.grok-imagine-video-1-5-preview.required` | list | [] |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.aspect_ratio.default` | str | 16:9 |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.aspect_ratio.enum[]` | str | 2:3 |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.aspect_ratio.enum[]` | str | 3:2 |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.aspect_ratio.enum[]` | str | 1:1 |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.aspect_ratio.enum[]` | str | 16:9 |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.aspect_ratio.enum[]` | str | 9:16 |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.aspect_ratio.type` | str | string |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.duration.type` | str | string |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.image_urls.type` | str | array |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.index.default` | int | 0 |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.index.maximum` | int | 5 |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.index.minimum` | int | 0 |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.index.type` | str | integer |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.mode.default` | str | normal |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.mode.enum[]` | str | fun |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.mode.enum[]` | str | normal |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.mode.enum[]` | str | spicy |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.mode.type` | str | string |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.nsfw_checker.type` | str | boolean |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.prompt.type` | str | string |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.resolution.default` | str | 480p |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.resolution.enum[]` | str | 480p |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.resolution.enum[]` | str | 720p |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.resolution.enum[]` | str | 1080p |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.resolution.type` | str | string |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.properties.task_id.type` | str | string |
| config/kie_media_schemas.json | `models.grok-imagine/image-to-video.required` | list | [] |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.aspect_ratio.default` | str | 2:3 |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.aspect_ratio.enum[]` | str | 2:3 |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.aspect_ratio.enum[]` | str | 3:2 |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.aspect_ratio.enum[]` | str | 1:1 |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.aspect_ratio.enum[]` | str | 16:9 |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.aspect_ratio.enum[]` | str | 9:16 |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.aspect_ratio.type` | str | string |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.duration.type` | str | number |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.mode.default` | str | normal |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.mode.enum[]` | str | fun |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.mode.enum[]` | str | normal |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.mode.enum[]` | str | spicy |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.mode.type` | str | string |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.nsfw_checker.type` | str | boolean |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.prompt.type` | str | string |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.resolution.default` | str | 480p |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.resolution.enum[]` | str | 480p |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.resolution.enum[]` | str | 720p |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.resolution.enum[]` | str | 1080p |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.properties.resolution.type` | str | string |
| config/kie_media_schemas.json | `models.grok-imagine/text-to-video.required[]` | str | prompt |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.duration.default` | int | 6 |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.duration.enum[]` | int | 4 |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.duration.enum[]` | int | 5 |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.duration.enum[]` | int | 6 |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.duration.enum[]` | int | 7 |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.duration.enum[]` | int | 8 |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.duration.enum[]` | int | 9 |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.duration.enum[]` | int | 10 |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.duration.enum[]` | int | 11 |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.duration.enum[]` | int | 12 |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.duration.enum[]` | int | 13 |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.duration.enum[]` | int | 14 |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.duration.enum[]` | int | 15 |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.duration.maximum` | int | 15 |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.duration.minimum` | int | 4 |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.duration.type` | str | integer |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.first_frame_url.type` | str | string |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.last_frame_url.type` | str | string |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.prompt.type` | str | string |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.resolution.default` | str | 2K |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.resolution.enum[]` | str | 768P |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.resolution.enum[]` | str | 2K |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.properties.resolution.type` | str | string |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.required[]` | str | prompt |
| config/kie_media_schemas.json | `models.minimax-h3/image-to-video.required[]` | str | duration |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.aspect_ratio.default` | str | adaptive |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.aspect_ratio.enum[]` | str | adaptive |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.aspect_ratio.enum[]` | str | 21:9 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.aspect_ratio.enum[]` | str | 16:9 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.aspect_ratio.enum[]` | str | 4:3 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.aspect_ratio.enum[]` | str | 1:1 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.aspect_ratio.enum[]` | str | 3:4 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.aspect_ratio.enum[]` | str | 9:16 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.aspect_ratio.type` | str | string |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.duration.default` | int | 6 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.duration.enum[]` | int | 4 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.duration.enum[]` | int | 5 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.duration.enum[]` | int | 6 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.duration.enum[]` | int | 7 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.duration.enum[]` | int | 8 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.duration.enum[]` | int | 9 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.duration.enum[]` | int | 10 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.duration.enum[]` | int | 11 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.duration.enum[]` | int | 12 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.duration.enum[]` | int | 13 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.duration.enum[]` | int | 14 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.duration.enum[]` | int | 15 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.duration.maximum` | int | 15 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.duration.minimum` | int | 4 |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.duration.type` | str | integer |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.prompt.type` | str | string |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.reference_audio_urls.type` | str | array |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.reference_image_urls.type` | str | array |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.reference_video_urls.type` | str | array |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.resolution.default` | str | 2K |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.resolution.enum[]` | str | 768P |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.resolution.enum[]` | str | 2K |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.properties.resolution.type` | str | string |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.required[]` | str | prompt |
| config/kie_media_schemas.json | `models.minimax-h3/reference-to-video.required[]` | str | duration |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.aspect_ratio.enum[]` | str | 21:9 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.aspect_ratio.enum[]` | str | 16:9 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.aspect_ratio.enum[]` | str | 4:3 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.aspect_ratio.enum[]` | str | 1:1 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.aspect_ratio.enum[]` | str | 3:4 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.aspect_ratio.enum[]` | str | 9:16 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.aspect_ratio.type` | str | string |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.duration.default` | int | 6 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.duration.enum[]` | int | 4 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.duration.enum[]` | int | 5 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.duration.enum[]` | int | 6 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.duration.enum[]` | int | 7 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.duration.enum[]` | int | 8 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.duration.enum[]` | int | 9 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.duration.enum[]` | int | 10 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.duration.enum[]` | int | 11 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.duration.enum[]` | int | 12 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.duration.enum[]` | int | 13 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.duration.enum[]` | int | 14 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.duration.enum[]` | int | 15 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.duration.maximum` | int | 15 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.duration.minimum` | int | 4 |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.duration.type` | str | integer |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.prompt.type` | str | string |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.resolution.default` | str | 2K |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.resolution.enum[]` | str | 768P |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.resolution.enum[]` | str | 2K |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.properties.resolution.type` | str | string |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.required[]` | str | prompt |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.required[]` | str | aspect_ratio |
| config/kie_media_schemas.json | `models.minimax-h3/text-to-video.required[]` | str | duration |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.aspect_ratio.default` | str | adaptive |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.aspect_ratio.enum[]` | str | adaptive |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.aspect_ratio.enum[]` | str | 16:9 |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.aspect_ratio.enum[]` | str | 4:3 |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.aspect_ratio.enum[]` | str | 1:1 |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.aspect_ratio.enum[]` | str | 3:4 |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.aspect_ratio.enum[]` | str | 9:16 |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.aspect_ratio.type` | str | string |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.audio.default` | bool | true |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.audio.type` | str | boolean |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.duration.default` | int | 5 |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.duration.maximum` | int | 30 |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.duration.minimum` | int | 2 |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.duration.type` | str | integer |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.first_frame_url.type` | str | string |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.last_frame_url.type` | str | string |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.nsfw_checker.type` | str | boolean |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.prompt.type` | str | string |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.reference_image_urls.type` | str | array |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.resolution.default` | str | 1080P |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.resolution.enum[]` | str | 480P |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.resolution.enum[]` | str | 720P |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.resolution.enum[]` | str | 1080P |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.resolution.type` | str | string |
| config/kie_media_schemas.json | `models.wan/3-0-video.properties.seed.type` | str | integer |
| config/kie_media_schemas.json | `models.wan/3-0-video.required[]` | str | prompt |
| config/knowledge.json | `_doc` | str | The instance's model knowledge (dated declarations). Applied with `walter-router declare` (idempotent). Leaderboards rank; this file says what each model is FOR, what it demands, and which words of a request call for it. Signals are matched accent- and case-insensitively on whole words. |
| config/knowledge.json | `affinities` | list | [] |
| config/knowledge.json | `decision._note` | str | Modèle de décision (intent + tri). Le meilleur vient du cycle 48 h (tâche 'decision', AA Decision Index). best_first (2026-10-14) = le meilleur (Jev 1.13 aujourd'hui), puis Mercury Decide gratuit, puis Clef (Workers AI) en dernier recours ; free_first = l'inverse (choix du 2026-10-04). |
| config/knowledge.json | `decision.order` | str | best_first |
| config/knowledge.json | `levels._doc` | str | The instance's text tiers, determined by the tier method (walter_router/tiers.py, docs/TIERS.md): strict AA Pareto frontier of callable model x reasoning level at real provider cost; L1 = first knee above 35 AA; L2 = best points-per-extra-dollar from L1; L3 = best points-per-extra-dollar from L2 within 5 points of the ceiling. Recomputed nightly; a different result raises one 'tier' alert, the owner adopts or ignores. pin = model_id/variant. |
| config/knowledge.json | `levels.general.L1.description` | str | Quotidien et tâches légères : GPT-6 Luna en raisonnement max (38,1 AA, 0,020 $/tâche, inclus Codex). |
| config/knowledge.json | `levels.general.L1.evidence` | str | frontière AA : +467 pts/$ depuis Luna xhigh ; domine MiMo 2.6 Flash (37,9 pour 0,062 $) |
| config/knowledge.json | `levels.general.L1.label` | str | Économique |
| config/knowledge.json | `levels.general.L1.pin` | str | gpt-6-luna/max |
| config/knowledge.json | `levels.general.L1.provider` | str | codex |
| config/knowledge.json | `levels.general.L1.watch` | str | none |
| config/knowledge.json | `levels.general.L2.description` | str | Analyse, comparatif, rédaction soignée : GPT-6.1 Sol en raisonnement medium (47,8 AA, 0,064 $/tâche, inclus Codex). |
| config/knowledge.json | `levels.general.L2.evidence` | str | coude de Sol : 229 pts/$ jusqu'à medium, puis 78 (high), 36 (xhigh), 8 (max) |
| config/knowledge.json | `levels.general.L2.label` | str | Intermédiaire |
| config/knowledge.json | `levels.general.L2.pin` | str | gpt-6-1-sol/medium |
| config/knowledge.json | `levels.general.L2.provider` | str | codex |
| config/knowledge.json | `levels.general.L2.watch` | str | none |
| config/knowledge.json | `levels.general.L3.description` | str | Raisonnement le plus exigeant, enjeux importants : Claude Opus 5.5 en high (53,6 AA, 0,73 $/tâche). |
| config/knowledge.json | `levels.general.L3.evidence` | str | coude du haut : 14,5 pts/$ jusqu'à Opus high, puis 3,7 (xhigh), 1,6 (max) ; repli Astra xhigh via Codex (52,4) |
| config/knowledge.json | `levels.general.L3.fallback` | str | gpt-6-astra/xhigh |
| config/knowledge.json | `levels.general.L3.label` | str | Haut de gamme |
| config/knowledge.json | `levels.general.L3.pin` | str | claude-opus-5-5/high |
| config/knowledge.json | `levels.general.L3.provider` | str | kie |
| config/knowledge.json | `levels.general.L3.watch` | str | none |
| config/knowledge.json | `postes._doc` | str | Fiches de poste (2026-10-02): weights over model attributes (0-100 each, see walter_router/postes.py). min_context in tokens. The orchestrator poste is compared with the model Hermes actually runs; a clearly better one (>= margin points) is proposed to the owner, never switched automatically. |
| config/knowledge.json | `postes.agent_worker.label` | str | Sous-agent d'exécution (walter_run) |
| config/knowledge.json | `postes.agent_worker.margin` | float | 3.0 |
| config/knowledge.json | `postes.agent_worker.min_context` | int | 200000 |
| config/knowledge.json | `postes.agent_worker.weights.access` | float | 0.1 |
| config/knowledge.json | `postes.agent_worker.weights.agentic` | float | 0.35 |
| config/knowledge.json | `postes.agent_worker.weights.intelligence` | float | 0.3 |
| config/knowledge.json | `postes.agent_worker.weights.reliability` | float | 0.2 |
| config/knowledge.json | `postes.agent_worker.weights.speed` | float | 0.05 |
| config/knowledge.json | `postes.agent_worker.why` | str | Exécute des tâches longues avec outils : agentique et intelligence d'abord. |
| config/knowledge.json | `postes.orchestrator.label` | str | Orchestrateur de Walter |
| config/knowledge.json | `postes.orchestrator.margin` | float | 3.0 |
| config/knowledge.json | `postes.orchestrator.min_context` | int | 400000 |
| config/knowledge.json | `postes.orchestrator.weights.access` | float | 0.15 |
| config/knowledge.json | `postes.orchestrator.weights.agentic` | float | 0.3 |
| config/knowledge.json | `postes.orchestrator.weights.intelligence` | float | 0.25 |
| config/knowledge.json | `postes.orchestrator.weights.reliability` | float | 0.15 |
| config/knowledge.json | `postes.orchestrator.weights.speed` | float | 0.15 |
| config/knowledge.json | `postes.orchestrator.why` | str | Mène la conversation et pilote les outils : fiabilité des appels d'outils, intelligence, peu d'hallucinations, réactivité, et accès par abonnement (il tourne en permanence). |
| config/knowledge.json | `profiles.gemini-omni-flash-1-1.access_note` | str | Crédits mensuels gratuits via l'abonnement Gemini AI Pro, dans l'interface Flow (pas d'API). |
| config/knowledge.json | `profiles.gemini-omni-flash-1-1.cost_note` | str | 0 $ tant qu'il reste des crédits Flow du mois. |
| config/knowledge.json | `profiles.gemini-omni-flash-1-1.declared_at` | str | 2026-10-02 |
| config/knowledge.json | `profiles.gemini-omni-flash-1-1.effort` | str | guided |
| config/knowledge.json | `profiles.gemini-omni-flash-1-1.note` | str | 2026-10-02 : très bon en UGC. |
| config/knowledge.json | `profiles.gemini-omni-flash-1-1.strengths[]` | str | ugc |
| config/knowledge.json | `profiles.gemini-omni-flash-1-1.strengths[]` | str | realism |
| config/knowledge.json | `profiles.gemini-omni-flash-1-1.weaknesses` | list | [] |
| config/knowledge.json | `profiles.gemini-omni-flash-1-1.workflow[]` | str | Générer dans Flow (interface web Google) en pilotant l'interface, avec les crédits mensuels gratuits de l'abonnement Gemini AI Pro |
| config/knowledge.json | `profiles.gemini-omni-flash-1-1.workflow[]` | str | Si les crédits sont épuisés : Kie en payant (prix par seconde du catalogue) |
| config/knowledge.json | `profiles.gpt-6-luna.access_note` | str | Inclus dans l'abonnement ChatGPT (Codex). |
| config/knowledge.json | `profiles.gpt-6-luna.declared_at` | str | 2026-10-02 |
| config/knowledge.json | `profiles.gpt-6-luna.effort` | str | direct |
| config/knowledge.json | `profiles.gpt-6-luna.note` | str | 2026-10-02 : préféré à MiMo 2.6 Flash à niveau égal, surtout avec l'abonnement Codex. |
| config/knowledge.json | `profiles.gpt-6-luna.strengths[]` | str | fast |
| config/knowledge.json | `profiles.gpt-6-luna.strengths[]` | str | cheap |
| config/knowledge.json | `profiles.gpt-6-luna.strengths[]` | str | subscription |
| config/knowledge.json | `profiles.grok-imagine-video-1-5.cost_note` | str | Vraiment pas cher sur Kie, mais pas au niveau des autres. |
| config/knowledge.json | `profiles.grok-imagine-video-1-5.declared_at` | str | 2026-10-02 |
| config/knowledge.json | `profiles.grok-imagine-video-1-5.effort` | str | direct |
| config/knowledge.json | `profiles.grok-imagine-video-1-5.note` | str | 2026-10-02. |
| config/knowledge.json | `profiles.grok-imagine-video-1-5.strengths[]` | str | cheap |
| config/knowledge.json | `profiles.grok-imagine-video-1-5.strengths[]` | str | drafts |
| config/knowledge.json | `profiles.grok-imagine-video-1-5.weaknesses[]` | str | lower_quality |
| config/knowledge.json | `profiles.grok-imagine-video-1-5.workflow[]` | str | Prompt direct ; 480p/720p via Kie |
| config/knowledge.json | `profiles.minimax-h3.content_policy` | str | permissive |
| config/knowledge.json | `profiles.minimax-h3.cost_note` | str | Meilleur ratio qualité/prix, surtout via Kie.ai. |
| config/knowledge.json | `profiles.minimax-h3.declared_at` | str | 2026-10-02 |
| config/knowledge.json | `profiles.minimax-h3.effort` | str | direct |
| config/knowledge.json | `profiles.minimax-h3.note` | str | 2026-10-02 : bonne balance, meilleur ratio, très bon en scènes d'action ; open source et peut-être unrestricted (à vérifier). |
| config/knowledge.json | `profiles.minimax-h3.strengths[]` | str | balanced |
| config/knowledge.json | `profiles.minimax-h3.strengths[]` | str | value |
| config/knowledge.json | `profiles.minimax-h3.strengths[]` | str | action |
| config/knowledge.json | `profiles.minimax-h3.weaknesses` | list | [] |
| config/knowledge.json | `profiles.minimax-h3.workflow[]` | str | Prompt direct ; 768p via Kie pour le meilleur prix |
| config/knowledge.json | `profiles.seedance-2-5.cost_note` | str | Le plus cher du panier : à réserver aux rendus qui le justifient. |
| config/knowledge.json | `profiles.seedance-2-5.declared_at` | str | 2026-10-02 |
| config/knowledge.json | `profiles.seedance-2-5.effort` | str | workflow |
| config/knowledge.json | `profiles.seedance-2-5.note` | str | 2026-10-02 : le top du top, mais demande un workflow avec création de références et un prompting adapté. |
| config/knowledge.json | `profiles.seedance-2-5.strengths[]` | str | premium |
| config/knowledge.json | `profiles.seedance-2-5.strengths[]` | str | cinematic |
| config/knowledge.json | `profiles.seedance-2-5.strengths[]` | str | character_consistency |
| config/knowledge.json | `profiles.seedance-2-5.strengths[]` | str | storytelling |
| config/knowledge.json | `profiles.seedance-2-5.weaknesses[]` | str | most_expensive |
| config/knowledge.json | `profiles.seedance-2-5.weaknesses[]` | str | needs_preparation |
| config/knowledge.json | `profiles.seedance-2-5.workflow[]` | str | Créer les références d'abord (personnages, décor, produit) avec le modèle image favori, en planche cohérente |
| config/knowledge.json | `profiles.seedance-2-5.workflow[]` | str | Adapter le prompt à Seedance : découpage plan par plan, cadrage et mouvement de caméra, action, durée, références jointes |
| config/knowledge.json | `profiles.seedance-2-5.workflow[]` | str | Valider en 480p/720p, puis rendu final en 1080p ou 4K |
| config/knowledge.json | `profiles.seedance-2-5.workflow[]` | str | Router le rendu sur le provider le moins cher à résolution égale (OpenRouter aujourd'hui ; 4K seulement chez OpenRouter) |
| config/knowledge.json | `retired_roles._tasks[]` | str | text_to_video |
| config/knowledge.json | `retired_roles._tasks[]` | str | image_to_video |
| config/knowledge.json | `retired_roles.reason` | str | 2026-10-02 : Omni 1.1 n'est plus le « meilleur ratio » (c'est H3) mais le choix UGC. |
| config/knowledge.json | `retired_roles.roles[]` | str | value |
| config/knowledge.json | `roles._tasks[]` | str | text_to_video |
| config/knowledge.json | `roles._tasks[]` | str | image_to_video |
| config/knowledge.json | `roles.action.description` | str | Scènes d'action, mouvement rapide, pour pas cher. |
| config/knowledge.json | `roles.action.label` | str | Action |
| config/knowledge.json | `roles.action.model` | str | minimax-h3 |
| config/knowledge.json | `roles.action.priority` | int | 20 |
| config/knowledge.json | `roles.action.provider` | str | kie |
| config/knowledge.json | `roles.action.signals[]` | str | action |
| config/knowledge.json | `roles.action.signals[]` | str | combat |
| config/knowledge.json | `roles.action.signals[]` | str | bagarre |
| config/knowledge.json | `roles.action.signals[]` | str | baston |
| config/knowledge.json | `roles.action.signals[]` | str | poursuite |
| config/knowledge.json | `roles.action.signals[]` | str | course poursuite |
| config/knowledge.json | `roles.action.signals[]` | str | explosion |
| config/knowledge.json | `roles.action.signals[]` | str | cascade |
| config/knowledge.json | `roles.action.signals[]` | str | fight |
| config/knowledge.json | `roles.action.signals[]` | str | chase |
| config/knowledge.json | `roles.action.signals[]` | str | sport |
| config/knowledge.json | `roles.action.signals[]` | str | drift |
| config/knowledge.json | `roles.action.signals[]` | str | dynamique |
| config/knowledge.json | `roles.action.signals[]` | str | mouvement rapide |
| config/knowledge.json | `roles.action.signals[]` | str | arts martiaux |
| config/knowledge.json | `roles.action.signals[]` | str | h3 |
| config/knowledge.json | `roles.action.signals[]` | str | minimax |
| config/knowledge.json | `roles.action.watch` | str | dominance |
| config/knowledge.json | `roles.budget.description` | str | Essais, brouillons, beaucoup de variantes, quand le prix compte plus que la qualité. |
| config/knowledge.json | `roles.budget.label` | str | Budget / brouillon |
| config/knowledge.json | `roles.budget.model` | str | grok-imagine-video-1-5 |
| config/knowledge.json | `roles.budget.priority` | int | 10 |
| config/knowledge.json | `roles.budget.provider` | str | kie |
| config/knowledge.json | `roles.budget.signals[]` | str | pas cher |
| config/knowledge.json | `roles.budget.signals[]` | str | brouillon |
| config/knowledge.json | `roles.budget.signals[]` | str | test |
| config/knowledge.json | `roles.budget.signals[]` | str | essai |
| config/knowledge.json | `roles.budget.signals[]` | str | maquette |
| config/knowledge.json | `roles.budget.signals[]` | str | previsualisation |
| config/knowledge.json | `roles.budget.signals[]` | str | preview |
| config/knowledge.json | `roles.budget.signals[]` | str | draft |
| config/knowledge.json | `roles.budget.signals[]` | str | variantes |
| config/knowledge.json | `roles.budget.signals[]` | str | batch |
| config/knowledge.json | `roles.budget.signals[]` | str | economique |
| config/knowledge.json | `roles.budget.signals[]` | str | low cost |
| config/knowledge.json | `roles.budget.signals[]` | str | grok |
| config/knowledge.json | `roles.budget.watch` | str | dominance |
| config/knowledge.json | `roles.default.description` | str | Demande vidéo sans objectif particulier : bonne balance qualité/prix, direct, sans préparation. |
| config/knowledge.json | `roles.default.label` | str | Équilibré |
| config/knowledge.json | `roles.default.model` | str | minimax-h3 |
| config/knowledge.json | `roles.default.priority` | int | 0 |
| config/knowledge.json | `roles.default.provider` | str | kie |
| config/knowledge.json | `roles.default.signals` | list | [] |
| config/knowledge.json | `roles.default.watch` | str | dominance |
| config/knowledge.json | `roles.premium.description` | str | Rendu final haut de gamme : pub, clip, film, personnage récurrent. Lance le workflow références + prompt adapté. |
| config/knowledge.json | `roles.premium.label` | str | Premium / cinématique |
| config/knowledge.json | `roles.premium.model` | str | seedance-2-5 |
| config/knowledge.json | `roles.premium.priority` | int | 40 |
| config/knowledge.json | `roles.premium.provider` | NoneType | — |
| config/knowledge.json | `roles.premium.signals[]` | str | pub |
| config/knowledge.json | `roles.premium.signals[]` | str | publicite |
| config/knowledge.json | `roles.premium.signals[]` | str | publicitaire |
| config/knowledge.json | `roles.premium.signals[]` | str | spot |
| config/knowledge.json | `roles.premium.signals[]` | str | cinematique |
| config/knowledge.json | `roles.premium.signals[]` | str | cinema |
| config/knowledge.json | `roles.premium.signals[]` | str | film |
| config/knowledge.json | `roles.premium.signals[]` | str | court metrage |
| config/knowledge.json | `roles.premium.signals[]` | str | clip |
| config/knowledge.json | `roles.premium.signals[]` | str | trailer |
| config/knowledge.json | `roles.premium.signals[]` | str | bande annonce |
| config/knowledge.json | `roles.premium.signals[]` | str | haut de gamme |
| config/knowledge.json | `roles.premium.signals[]` | str | premium |
| config/knowledge.json | `roles.premium.signals[]` | str | luxe |
| config/knowledge.json | `roles.premium.signals[]` | str | qualite max |
| config/knowledge.json | `roles.premium.signals[]` | str | meilleure qualite |
| config/knowledge.json | `roles.premium.signals[]` | str | top qualite |
| config/knowledge.json | `roles.premium.signals[]` | str | rendu final |
| config/knowledge.json | `roles.premium.signals[]` | str | storytelling |
| config/knowledge.json | `roles.premium.signals[]` | str | personnage recurrent |
| config/knowledge.json | `roles.premium.signals[]` | str | coherence des personnages |
| config/knowledge.json | `roles.premium.signals[]` | str | seedance |
| config/knowledge.json | `roles.premium.watch` | str | quality |
| config/knowledge.json | `roles.ugc.description` | str | Contenu type créateur : face caméra, témoignage, avis client, TikTok/Reels. Via Flow avec les crédits gratuits. |
| config/knowledge.json | `roles.ugc.label` | str | UGC |
| config/knowledge.json | `roles.ugc.model` | str | gemini-omni-flash-1-1 |
| config/knowledge.json | `roles.ugc.priority` | int | 30 |
| config/knowledge.json | `roles.ugc.provider` | str | google-flow |
| config/knowledge.json | `roles.ugc.signals[]` | str | ugc |
| config/knowledge.json | `roles.ugc.signals[]` | str | temoignage |
| config/knowledge.json | `roles.ugc.signals[]` | str | face camera |
| config/knowledge.json | `roles.ugc.signals[]` | str | avis client |
| config/knowledge.json | `roles.ugc.signals[]` | str | tiktok |
| config/knowledge.json | `roles.ugc.signals[]` | str | reel |
| config/knowledge.json | `roles.ugc.signals[]` | str | reels |
| config/knowledge.json | `roles.ugc.signals[]` | str | story |
| config/knowledge.json | `roles.ugc.signals[]` | str | stories |
| config/knowledge.json | `roles.ugc.signals[]` | str | selfie |
| config/knowledge.json | `roles.ugc.signals[]` | str | influenceur |
| config/knowledge.json | `roles.ugc.signals[]` | str | influenceuse |
| config/knowledge.json | `roles.ugc.signals[]` | str | unboxing |
| config/knowledge.json | `roles.ugc.signals[]` | str | vlog |
| config/knowledge.json | `roles.ugc.signals[]` | str | createur |
| config/knowledge.json | `roles.ugc.signals[]` | str | testimonial |
| config/knowledge.json | `roles.ugc.signals[]` | str | authentique |
| config/knowledge.json | `roles.ugc.signals[]` | str | smartphone |
| config/knowledge.json | `roles.ugc.signals[]` | str | omni |
| config/knowledge.json | `roles.ugc.signals[]` | str | flow |
| config/knowledge.json | `roles.ugc.watch` | str | none |
| config/knowledge.json | `task_hints.3d` | str | Créer une scène 3D interactive ou du WebGL/Three.js en code |
| config/knowledge.json | `task_hints.calculation` | str | Calcul arithmétique ou conversion d'unités exacte |
| config/knowledge.json | `task_hints.coding` | str | Écrire, corriger, expliquer ou relire du code, scripts, API, back-end, automatisation |
| config/knowledge.json | `task_hints.dataviz` | str | Créer un graphique ou une visualisation de données en code |
| config/knowledge.json | `task_hints.document` | str | Analyser un fichier fourni : PDF, contrat, rapport, tableur, document joint |
| config/knowledge.json | `task_hints.frontend` | str | Créer un site web ou une landing page (HTML/CSS/JS, design web) |
| config/knowledge.json | `task_hints.fullstack` | str | Construire une application web complète avec front-end, back-end et base de données |
| config/knowledge.json | `task_hints.gamedev` | str | Créer un petit jeu jouable (HTML5/canvas) en code |
| config/knowledge.json | `task_hints.general` | str | Réponse texte : question, explication, résumé, rédaction, traduction, conseil, analyse ou comparaison (pas de code, pas de média, pas de fichier joint) |
| config/knowledge.json | `task_hints.graphic_design` | str | Créer une affiche, un flyer, une bannière, un visuel graphique avec texte |
| config/knowledge.json | `task_hints.image_edit` | str | Modifier ou retoucher une image existante (changer le fond, ajouter/retirer un objet, style) |
| config/knowledge.json | `task_hints.image_to_video` | str | Animer une image ou une photo existante pour en faire une vidéo |
| config/knowledge.json | `task_hints.logo` | str | Créer un logo ou une identité visuelle |
| config/knowledge.json | `task_hints.mobile_app` | str | Construire une application mobile |
| config/knowledge.json | `task_hints.music` | str | Composer ou générer une musique, une chanson, un jingle |
| config/knowledge.json | `task_hints.research` | str | Recherche web d'informations récentes ou de sources : actualités, prix du moment, qui/quand/où sur un fait actuel |
| config/knowledge.json | `task_hints.speech_to_speech` | str | Conversation vocale en temps réel |
| config/knowledge.json | `task_hints.svg` | str | Créer une illustration ou une icône vectorielle SVG en code |
| config/knowledge.json | `task_hints.text_to_image` | str | Générer une image, une photo, une illustration à partir d'une description |
| config/knowledge.json | `task_hints.text_to_video` | str | Générer une vidéo (clip, scène animée, pub vidéo, plan cinéma) à partir d'une description |
| config/knowledge.json | `task_hints.tts` | str | Lire un texte à voix haute, générer une voix off ou un audio parlé |
| config/knowledge.json | `task_hints.ui_component` | str | Créer un composant d'interface isolé (bouton, formulaire, carte, tableau de bord) en code |
| config/knowledge.json | `task_hints.video_edit` | str | Modifier une vidéo existante (changer le style, remplacer un élément, prolonger) |
| config/knowledge.json | `task_hints.vision` | str | Analyser ou décrire une image ou une photo fournie (que voit-on, lire du texte dans l'image) |
| config/knowledge.json | `task_hints.weather` | str | Météo actuelle ou prévisions pour un lieu |
| config/knowledge.json | `unrestricted_favourites` | list | [] |
| config/knowledge.json | `unrestricted_signals[]` | str | sans censure |
| config/knowledge.json | `unrestricted_signals[]` | str | uncensored |
| config/knowledge.json | `unrestricted_signals[]` | str | unrestricted |
| config/knowledge.json | `unrestricted_signals[]` | str | sans restriction |
| config/knowledge.json | `unrestricted_signals[]` | str | nsfw |
| config/knowledge.json | `unrestricted_signals[]` | str | explicite |
| config/knowledge.json | `unrestricted_signals[]` | str | non censure |
| config/media_models.json | `_doc` | str | How each media favourite is called. kie: market path per mode + where images go; openrouter: the OpenRouter model id (generic /api/v1/videos or /api/v1/images). prompt_style: how the economic model rewrites the user's request for this model. |
| config/media_models.json | `models.gemini-3-8-flash-tts.kie.tts` | str | google/gemini-3-8-flash-tts |
| config/media_models.json | `models.gemini-3-8-flash-tts.kind` | str | audio |
| config/media_models.json | `models.gemini-omni-flash-1-1.kie.first_frame` | str | first_frame_url |
| config/media_models.json | `models.gemini-omni-flash-1-1.kie.i2v` | str | google/gemini-omni-flash-1-1 |
| config/media_models.json | `models.gemini-omni-flash-1-1.kie.references` | str | image_urls |
| config/media_models.json | `models.gemini-omni-flash-1-1.kie.t2v` | str | google/gemini-omni-flash-1-1 |
| config/media_models.json | `models.gemini-omni-flash-1-1.kind` | str | video |
| config/media_models.json | `models.gemini-omni-flash-1-1.prompt_style` | str | A natural English prompt for an authentic creator-style (UGC) video: who speaks, framing (selfie / face camera), setting, what is said, tone. Keep every requested element. |
| config/media_models.json | `models.gpt-image-2-5-flare.kie.i2i` | str | gpt-image-2-5-flare-image-to-image |
| config/media_models.json | `models.gpt-image-2-5-flare.kie.images` | str | input_urls |
| config/media_models.json | `models.gpt-image-2-5-flare.kie.t2i` | str | gpt-image-2-5-flare-text-to-image |
| config/media_models.json | `models.gpt-image-2-5-flare.kind` | str | image |
| config/media_models.json | `models.gpt-image-2-5-flare.openrouter` | str | openai/gpt-image-2.5-flare |
| config/media_models.json | `models.gpt-image-2-5-flare.prompt_style` | str | A detailed English image prompt: subject, setting, lighting, composition, style. Keep every requested element. |
| config/media_models.json | `models.gpt-image-2-5-sunburst.kie.i2i` | str | gpt-image-2-5-sunburst-image-to-image |
| config/media_models.json | `models.gpt-image-2-5-sunburst.kie.images` | str | input_urls |
| config/media_models.json | `models.gpt-image-2-5-sunburst.kie.t2i` | str | gpt-image-2-5-sunburst-text-to-image |
| config/media_models.json | `models.gpt-image-2-5-sunburst.kind` | str | image |
| config/media_models.json | `models.gpt-image-2-5-sunburst.openrouter` | str | openai/gpt-image-2.5-sunburst |
| config/media_models.json | `models.gpt-image-2-5-sunburst.prompt_style` | str | A detailed English image prompt: main subject, setting/background, lighting, composition and camera framing, style and mood. Keep EVERY element the user asked for (the setting especially) and add nothing he would not want. |
| config/media_models.json | `models.grok-imagine-video-1-5.kie.first_frame` | str | image_urls |
| config/media_models.json | `models.grok-imagine-video-1-5.kie.i2v` | str | grok-imagine-video-1-5-preview |
| config/media_models.json | `models.grok-imagine-video-1-5.kie.references` | str | image_urls |
| config/media_models.json | `models.grok-imagine-video-1-5.kie.t2v` | str | grok-imagine-video-1-5-preview |
| config/media_models.json | `models.grok-imagine-video-1-5.kind` | str | video |
| config/media_models.json | `models.grok-imagine-video-1-5.openrouter` | str | x-ai/grok-imagine-video-1.5 |
| config/media_models.json | `models.grok-imagine-video-1-5.prompt_style` | str | A short English video prompt: subject, action, camera, setting. |
| config/media_models.json | `models.heygen-video-1.kind` | str | video |
| config/media_models.json | `models.heygen-video-1.openrouter` | str | heygen/heygen-video-1 |
| config/media_models.json | `models.heygen-video-1.prompt_style` | str | A vivid English video prompt: subject, action and motion, camera, setting, lighting, sound if relevant. Keep every requested element. |
| config/media_models.json | `models.minimax-h3.kie.first_frame` | str | first_frame_url |
| config/media_models.json | `models.minimax-h3.kie.i2v` | str | minimax-h3/image-to-video |
| config/media_models.json | `models.minimax-h3.kie.r2v` | str | minimax-h3/reference-to-video |
| config/media_models.json | `models.minimax-h3.kie.references` | str | reference_image_urls |
| config/media_models.json | `models.minimax-h3.kie.t2v` | str | minimax-h3/text-to-video |
| config/media_models.json | `models.minimax-h3.kind` | str | video |
| config/media_models.json | `models.minimax-h3.openrouter` | str | minimax/hailuo-3 |
| config/media_models.json | `models.minimax-h3.prompt_style` | str | A vivid English video prompt: subject, action and motion, camera, setting, lighting, sound if relevant. Keep every requested element. |
| config/media_models.json | `models.seedance-2-5.kie.first_frame` | str | first_frame_url |
| config/media_models.json | `models.seedance-2-5.kie.i2v` | str | bytedance/seedance-2-5 |
| config/media_models.json | `models.seedance-2-5.kie.r2v` | str | bytedance/seedance-2-5 |
| config/media_models.json | `models.seedance-2-5.kie.references` | str | reference_image_urls |
| config/media_models.json | `models.seedance-2-5.kie.t2v` | str | bytedance/seedance-2-5 |
| config/media_models.json | `models.seedance-2-5.kind` | str | video |
| config/media_models.json | `models.seedance-2-5.openrouter` | str | bytedance/seedance-2.5 |
| config/media_models.json | `models.seedance-2-5.prompt_style` | str | An English shot-by-shot video prompt for Seedance: for each shot, framing, camera movement, action and timing; consistent characters; reference the attached reference image as the visual anchor. Keep every requested element. |
| config/media_models.json | `models.seedance-2-5.workflow` | str | reference_first |
| config/media_models.json | `models.suno.kie.music` | str | ai-music-api/generate |
| config/media_models.json | `models.suno.kind` | str | music |
| config/media_models.json | `models.suno.prompt_style` | str | Suno style tags in English (genre, mood, instruments, tempo) — max 200 characters. |
| config/media_models.json | `models.wan-3._note` | str | Kie wan/3-0-video (docs.kie.ai/market/wan/3-0-video.md, 2026-10-14): 2-30 s, 480P/720P/1080P (default 1080P = 0.16 $/s, hence 720p), audio on by default, nsfw_checker off by default. |
| config/media_models.json | `models.wan-3.defaults.resolution` | str | 720p |
| config/media_models.json | `models.wan-3.kie.first_frame` | str | first_frame_url |
| config/media_models.json | `models.wan-3.kie.i2v` | str | wan/3-0-video |
| config/media_models.json | `models.wan-3.kie.r2v` | str | wan/3-0-video |
| config/media_models.json | `models.wan-3.kie.references` | str | reference_image_urls |
| config/media_models.json | `models.wan-3.kie.t2v` | str | wan/3-0-video |
| config/media_models.json | `models.wan-3.kind` | str | video |
| config/media_models.json | `models.wan-3.openrouter` | str | alibaba/wan-3.0 |
| config/media_models.json | `models.wan-3.prompt_style` | str | A vivid English video prompt: subject, action and motion, camera movement, setting, lighting, sound if relevant. Keep every requested element. |
| config/providers.json | `_doc` | str | OpenAI-compatible providers whose live /models catalogue (with prices) is collected. The key is read at run time from the environment, else from the instance's vault (walter_router.instance.secret_value: Hermes .env, or walter-secrets declared keys) and sent as a header only. hermes_provider null = no Hermes provider: the Router runs it natively through walter-llm. |
| config/providers.json | `providers[].api` | str | https://api.arnict.com/v1 |
| config/providers.json | `providers[].hermes_provider` | str | arnict |
| config/providers.json | `providers[].key_env` | str | ARNICT_API_KEY |
| config/providers.json | `providers[].name` | str | Arnict AI |
| config/providers.json | `providers[].note` | str | Uncensored open-weights fine-tunes (GLM 5.3 Flash Uncensored...) |
| config/providers.json | `providers[].provider` | str | arnict |
| config/providers.json | `providers[].api` | str | https://api.venice.ai/api/v1 |
| config/providers.json | `providers[].hermes_provider` | NoneType | — |
| config/providers.json | `providers[].key_env` | str | VENICE_API_KEY |
| config/providers.json | `providers[].name` | str | Venice AI |
| config/providers.json | `providers[].note` | str | Venice inference (uncensored DeepSeek V4.1 Flash 1017, pay per token). |
| config/providers.json | `providers[].provider` | str | venice |
| config/subscriptions.json | `_doc` | str | the owner's subscriptions (declared by him), for information only: no routing effect (2026-10-14). Shown on the library page with two sources only: our own measurement (meters + the tokens W.Alter's runtimes really used, priced at list API rates) and SemiAnalysis' published plan values. Readings go to models.subscription_usage. |
| config/subscriptions.json | `semianalysis.date` | str | 2026-10-05 |
| config/subscriptions.json | `semianalysis.definition` | str | API-equivalent value = the plan's full monthly usage limit priced at first-party list API rates. |
| config/subscriptions.json | `semianalysis.report` | str | Anthropic Subscriptions Offer 5x+ More Value Than OpenAI |
| config/subscriptions.json | `semianalysis.url` | str | https://newsletter.semianalysis.com/p/anthropic-subscriptions-offer-5x |
| config/subscriptions.json | `semianalysis.workload_mix.cache_read` | float | 0.966 |
| config/subscriptions.json | `semianalysis.workload_mix.cache_write` | float | 0.026 |
| config/subscriptions.json | `semianalysis.workload_mix.input` | float | 0.004 |
| config/subscriptions.json | `semianalysis.workload_mix.output` | float | 0.003 |
| config/subscriptions.json | `subscriptions` | list | [] |
