"""English version of the library page (2026-10-14: « une version anglaise et française à choisir en bas »).

A translation pass over the final French HTML, so both pages share exactly the same layout: phrase table applied to
text nodes and to a few attributes (placeholder, title, aria-label), French decimals → English in text and chart
tooltips, JS strings and date locale, `lang` attribute and the selector state. Any French label added later stays
French until listed here (tests check the English page for leftover French words).
"""
from __future__ import annotations

import re

# Longest first is enforced at load time; exact substrings.
PHRASES = {
    # header / nav / tools
    "Bibliothèque des modèles — Walter Router": "Model library — Walter Router",
    "Bibliothèque des modèles": "Model library",
    "▶ Lancer le cycle complet": "▶ Run the full cycle",
    "Vue d'ensemble": "Overview", "Audio & musique": "Audio & music", "Décision": "Decision", "Texte": "Text",
    "Vidéo": "Video", "Mémoire & recherche": "Memory & search", "Rechercher": "Search", "$/recherche": "$/search", "Mes choix ≠ n°1": "My picks ≠ #1",
    # home
    "🧠 Niveaux de réflexion": "🧠 Reasoning levels",
    "Optimum de Pareto calculé par ta méthode sur la frontière AA": "Pareto optimum computed with your method on the AA frontier",
    "📈 Indice d'intelligence et coût par tâche": "📈 Intelligence index and cost per task",
    "combinaisons modèle × niveau de réflexion exécutables": "runnable model × reasoning-level combinations",
    "Coût AA officiel": "Official AA cost", "Coût réel": "Real cost", "Indice AA": "AA index",
    "Prix de référence publié par Artificial Analysis": "Reference price published by Artificial Analysis",
    "Recalculé avec le prix du fournisseur utilisé": "Recomputed with the price of the provider in use",
    "Modèles exécutables": "Runnable models", "Frontière de Pareto": "Pareto frontier", "Niveaux retenus": "Selected levels",
    "Abscisse : ": "X axis: ", "coût réel par tâche AA (meilleur fournisseur)": "real cost per AA task (best provider)",
    "coût officiel par tâche AA (prix de référence)": "official cost per AA task (reference price)",
    ", échelle logarithmique": ", log scale", "Indice AA en fonction du coût réel par tâche": "AA index vs real cost per task",
    "🎨 Spécialisations Design Arena": "🎨 Design Arena specialisations",
    "Rang du modèle retenu sur le classement Design Arena de chaque tâche":
        "Rank of the selected model on each task's Design Arena leaderboard",
    "N°1 Design Arena, si différent": "Design Arena #1, if different", "Modèle retenu": "Selected model",
    "Classement inaccessible : ": "Leaderboard unreachable: ",
    "Le router conserve sa dernière lecture valable pendant 21 jours.": "The router keeps its last valid reading for 21 days.",
    "Pas de données AA.": "No AA data.",
    # levels
    "Économique": "Economy", "Intermédiaire": "Intermediate", "Haut de gamme": "High end",
    "Quotidien : réponses courtes, résumés, petites rédactions": "Everyday: short answers, summaries, small writing",
    "Analyse en plusieurs étapes, comparaison, rédaction soignée": "Multi-step analysis, comparison, careful writing",
    "Raisonnement profond, synthèse, enjeu important": "Deep reasoning, synthesis, high stakes",
    "réflexion très élevée": "reasoning: very high", "réflexion maximale": "reasoning: maximum",
    "réflexion moyenne": "reasoning: medium", "réflexion élevée": "reasoning: high", "réflexion faible": "reasoning: low",
    "Fournisseurs (ordre, prix)": "Providers (order, price)", "Fournisseurs": "Providers", "Secours": "Fallback",
    "Abonnement": "Subscription", "Niveau": "Level", "Modèle": "Model", "Tâche": "Task", "Origine": "Origin",
    "Rang": "Rank", "Score /100 : moyenne pondérée des classements indiqués sous chaque tâche":
        "Score /100: weighted average of the leaderboards listed under each task",
    # origins
    "Ton choix": "Your pick", "Calculé": "Computed", "Méthode Pareto": "Pareto method", "Aucun modèle": "No model",
    # task labels (models.tasks)
    "Code / back-end / agentique": "Code / back-end / agentic", "Visualisation de données": "Data visualisation",
    "Modèle de décision avec image (navigation, traitement d'images en masse)":
        "Decision model with images (browsing, bulk image processing)",
    "Modèle de décision (routage d'intention, tri)": "Decision model (intent routing, triage)",
    "Analyse de document / PDF": "Document / PDF analysis", "Santé / médical": "Health / medical", "Juridique / droit": "Legal", "Sciences / recherche avancée": "Science / advanced research", "Long contexte (très longs documents)": "Long context (very long documents)", "Rédaction / qualité d'écriture": "Writing quality", "Ingénierie": "Engineering", "Finance / comptabilité / économie": "Finance / accounting / economics", "Stratégie / conseil / opérations": "Strategy / consulting / operations", "Cybersécurité": "Cybersecurity", "tâches de fond": "background jobs", "prix de revient": "cost price", "(abonnement)": "(subscription)", "(même modèle)": "(same model)", "— (un seul fournisseur)": "— (single provider)", "Kie (payant)": "Kie (paid)", " · puis ": " · then ", "du prix API": "of the API price", "Site web / landing": "Website / landing page",
    "Application full-stack (agent)": "Full-stack app (agent)", "Jeu (canvas / HTML5)": "Game (canvas / HTML5)",
    "Texte général (niveaux L1/L2/L3)": "General text (levels L1/L2/L3)", "Graphisme / affiche": "Graphic design / poster",
    "Retouche / édition d'image": "Image retouching / editing", "Animer une image": "Animate an image",
    "Logo / identité visuelle": "Logo / visual identity", "Application mobile (agent)": "Mobile app (agent)",
    "Résumé / compression de contexte": "Summarisation / context compression",
    "Extraction mémoire structurée": "Structured memory extraction",
    "Lecture du développement (tableau)": "Development reading (board)",
    "Aide texte pendant un appel vocal": "Text helper during a phone call",
    "Transcription (parole vers texte)": "Transcription (speech to text)",
    "Vectorisation (embeddings)": "Embeddings",
    "Reclassement de résultats (rerank)": "Result reranking",
    "Musique": "Music", "Recherche web": "Web search", "Conversation vocale temps réel": "Real-time voice conversation",
    "SVG / vectoriel": "SVG / vector", "Vidéo depuis texte": "Text to video", "Voix (lecture)": "Voice (text to speech)",
    "Composant d'interface": "UI component", "Édition de vidéo": "Video editing", "Analyse d'image": "Image analysis",
    "Météo": "Weather", "Calcul": "Calculation",
    # categories (models.preferences)
    "Budget / brouillon": "Budget / draft", "Équilibré": "Balanced", "Premium / cinématique": "Premium / cinematic",
    # data notes
    "n°1 mesuré : ": "measured #1: ", "(pas de fournisseur branché)": "(no provider wired)",
    "pas de fournisseur branché": "no provider wired",
    "(proposé par aucun de nos fournisseurs)": "(offered by none of our providers)",
    "Codex (abonnement) inclus": "Codex (subscription) included", "via Codex (abonnement)": "via Codex (subscription)",
    "Flow à la main": "Flow, by hand", "(si payant)": "(if paid)", "$/img estimé": "$/img estimated",
    "$/requête": "$/request", "(gratuit)": "(free)", "Codex (secours)": "Codex (fallback)",
    "Gemini AI Pro (crédits Flow)": "Gemini AI Pro (Flow credits)", "aucun modèle exécutable": "no runnable model",
    "AA ne teste pas encore la vision : classé sur l'index texte, parmi ceux qui lisent les images":
        "AA does not test vision yet: ranked on the text index, among models that read images",
    "pas encore classée sur ce benchmark": "not ranked on this benchmark yet", "version supérieure de ": "newer version of ",
    "Arena retouche d'image": "Arena image editing",
    # subscriptions tab
    "Abonnements": "Subscriptions",
    "Ce que tes forfaits valent au prix API : notre mesure sur ton compte et les chiffres publiés par SemiAnalysis. Information seulement, le routage ne change pas.":
        "What your plans are worth at API prices: our measurement on your account and the figures published by "
        "SemiAnalysis. Information only, routing is unchanged.",
    "Compteur et consommation des 7 derniers jours": "Meter and usage over the last 7 days",
    "Prix": "Price", "Utilisé par": "Used by", "Compteur hebdo": "Weekly meter", "Remise à zéro": "Resets", "Lus en cache": "Cache reads",
    "Valeur API par mois": "API value per month", "Valeur API": "API value",
    "Coût du million à ton rythme": "Cost per million at your pace", "Coût du million": "Cost per million",
    "par mois": "per month", "estimé, à calibrer": "estimated, to calibrate", "estimé": "estimated", "réel": "real",
    "non lu": "not read", "7 jours glissants": "rolling 7 days",
    "Capacité du forfait utilisé à 100 %": "Plan capacity at 100 % use", "× le prix": "× the price",
    "Tokens par mois": "Tokens per month", "Forfait entier": "Whole plan",
    "Notre mesure": "Our measurement", " points de compteur": " meter points",
    "en cours : il faut 3 points de compteur dans une même semaine": "in progress: needs 3 meter points within one week",
    "à calibrer avec le pourcentage hebdomadaire affiché par claude.ai": "to calibrate with the weekly percentage shown by claude.ai",
    "non inclus dans Pro (crédits payés au prix API)": "not included in Pro (credits paid at API price)",
    "Abonnements indisponibles : ": "Subscriptions unavailable: ",
    "Valeur API = tokens réellement consommés, au prix catalogue de l’éditeur. ":
        "API value = tokens actually used, at the vendor’s list price. ",
    "Tokens vus sur la VM : Hermes et Codex pour ChatGPT Plus, Claude Code pour Claude Pro. ":
        "Tokens seen on the VM: Hermes and Codex for ChatGPT Plus, Claude Code for Claude Pro. ",
    "Coût du million à ton rythme = prix de la semaine ÷ tokens de la semaine. ":
        "Cost per million at your pace = the week’s price ÷ the week’s tokens. ",
    "Notre mesure ChatGPT = valeur API consommée entre deux lectures du compteur ÷ points gagnés, ramenée à 100 % (un plancher : l’usage hors de la VM fait monter le compteur sans tokens vus ici). ":
        "Our ChatGPT measurement = API value used between two meter readings ÷ points gained, scaled to 100 % (a floor: "
        "usage outside the VM moves the meter without tokens seen here). ",
    "Compteur Claude estimé = entrée + écriture en cache + 5 × sortie, lectures en cache gratuites, sur une capacité tirée de SemiAnalysis tant qu’il n’est pas calibré. ":
        "Estimated Claude meter = input + cache writes + 5 × output, cache reads free, over a capacity taken from "
        "SemiAnalysis until it is calibrated. ",
    "SemiAnalysis, rapport du ": "SemiAnalysis, report of ",
    " : valeur du forfait entièrement utilisé, sur un usage agentique de ": ": value of the plan fully used, on an agentic workload with ",
    " % de lectures en cache ; tokens par mois = valeur ÷ prix moyen du million sur ce mélange.":
        " % cache reads; tokens per month = value ÷ average price per million on that mix.",
    " Md": " B",
    # footer
    "Modèles suivis": "Models tracked",
    "Classements recalculés le ": "Leaderboards recomputed on ",
    " ; cycle complet automatique toutes les 48 heures, page republiée après chacune de tes réponses.":
        "; full cycle every 48 hours, page republished after each of your answers.",
    "Origine : « Ton choix » = modèle fixé par toi ; « Calculé » = meilleur modèle exécutable selon les classements\npondérés ; « Méthode Pareto » = niveaux L1, L2, L3. Une ligne surlignée signale un choix de ta part différent du n°1 mesuré, avec la raison.":
        "Origin: “Your pick” = model you set; “Computed” = best runnable model on the weighted leaderboards; “Pareto "
        "method” = levels L1, L2, L3. A highlighted row marks a pick of yours that differs from the measured #1, with the reason.",
    "Prix : texte en dollars par million de tokens (entrée/sortie), image par image, vidéo par seconde (plage selon la résolution) ;\n« estimé » lorsque le fournisseur facture au token.":
        "Prices: text in dollars per million tokens (input/output), images per image, video per second (range by "
        "resolution); “estimated” when the provider bills per token.",
    "Page générée le ": "Page generated on ",
}
# words that must never survive in the English page (checked by the tests)
FRENCH_MARKERS = ("Fournisseur", "Secours", "Abonnement", "Modèle", "Tâche", "réflexion", "Calculé", "mesuré",
                  "Économique", "Vidéo", "Coût", "Rechercher", "Lancer", "généré", "estimé", "Équilibré")
JS = {
    "'Envoi…'": "'Sending…'", "'Enregistré, la page se met à jour…'": "'Saved, the page is updating…'", "'Refusé'": "'Refused'",
    "'Échec de l’envoi'": "'Sending failed'",
    "'Résilier ce plan ? Il sortira de tes abonnements (gardé dans l’historique).'": "'Cancel this plan? It leaves your plans (kept in the history).'",
    "Cycle en cours — ": "Cycle running — ", "'démarrage'": "'starting'", "Dernier cycle complet : ": "Last full cycle: ",
    "' (échec)'": "' (failed)'", "Statut indisponible": "Status unavailable",
    "Lancer maintenant le cycle complet ? Collecte des classements, recalcul, analyse par le modèle économique, notifications et republication de cette page (20 à 60 minutes).":
        "Run the full cycle now? Leaderboard collection, recomputation, analysis by the economy model, notifications and "
        "republication of this page (20 to 60 minutes).",
    "Lancement…": "Starting…", "Échec du lancement": "Launch failed", "'fr-FR'": "'en-GB'",
    "'Indice '": "'Index '", "' $ par tâche'": "' $ per task'",
}
STEPS = {"1/4 recherche et analyse": "1/4 research and analysis", "2/4 agent de recherche (modèle économique)": "2/4 research agent (economy model)", "3/4 analyse finale et notifications": "3/4 final analysis and notifications", "4/4 Hermes et page": "4/4 Hermes and page"}
PHRASES.update({k.replace("'", "&#x27;"): v.replace("'", "&#x27;") for k, v in list(PHRASES.items()) if "'" in k})
PHRASES.update({k.replace("&", "&amp;"): v.replace("&", "&amp;") for k, v in list(PHRASES.items()) if "&" in k and "&#" not in k})
PHRASES.update({
 "Ce que tes forfaits valent au prix API, le prix de revient d’un token par forfait (il entre dans le choix du fournisseur), ce que l’on sait de chaque plan, et la modification de tes plans.": "What your plans are worth at API prices, the cost price of a token per plan (it counts in the choice of provider), what is known about each plan, and editing your plans.",
 "Prix de revient d’un token": "Cost price of a token",
 "À ton rythme": "At your pace",
 "Forfait utilisé à 100 %": "Plan used at 100 %",
 "Valeur API par mois (rythme)": "API value per month (pace)",
 "Valeur API par mois (capacité)": "API value per month (capacity)",
 "Quota hebdo": "Weekly quota",
 "Âge de la mesure": "Age of the measure",
 "Prix de revient = prix du forfait ÷ valeur API qu’il transporte par mois, en part du prix API. Un chemin par abonnement passe en premier tant que son quota hebdomadaire reste sous 90 %, puis après les fournisseurs payants.": "Cost price = plan price ÷ API value it carries per month, as a share of the API price. A route through a plan goes first while its weekly quota stays under 90 %, then after the paid providers.",
 "Ce que l’on sait de chaque plan": "What is known about each plan",
 "Trouvé par": "Found by",
 "Quoi": "What",
 "Valeur": "Value",
 "valeur API par mois": "API value per month",
 "tokens par mois": "tokens per month",
 "messages par 5 h": "messages per 5 h",
 "messages par semaine": "messages per week",
 "prix par mois": "price per month",
 "limite": "limit",
 "événement": "event",
 "✍️ toi": "✍️ you",
 "📏 mesure": "📏 measure",
 "Modifier mes abonnements": "Edit my plans",
 "Aussi possible dans la discussion (« walter-router plans set … ») ; un mail de facturation qui ne correspond pas devient une proposition sur Telegram.": "Also possible in the conversation (« walter-router plans set … »); a billing e-mail that does not match becomes a proposal on Telegram.",
 "Nouvel abonnement": "New plan",
 "Identifiant": "Identifier",
 "Éditeur": "Vendor",
 "Prix par mois ($)": "Price per month ($)",
 "Modèles inclus": "Included models",
 "Enregistrer": "Save",
 "Résilier": "Cancel plan",
 "ex. google-ai-pro": "e.g. google-ai-pro",
 "ids séparés par des virgules": "comma-separated ids"
})
# Leaderboard labels ("Arena vidéo depuis texte", analysis.telegram._board_fr), shown on the page when a board is
# unreachable (2026-11-07: the banner was the only French left on the English page while Arena collection failed).
BOARD_TASKS_EN = {"vidéo depuis texte": "text to video", "animation d'image": "image animation", "retouche d'image": "image editing",
                  "voix": "voice", "musique": "music", "texte": "text", "fidélité (100 − WER)": "accuracy (100 − WER)",
                  "vitesse": "speed", "rerank latence": "rerank latency", "embeddings latence": "embeddings latency",
                  "recherche en français": "French retrieval"}
_SOURCES = ("AA", "AA Decision", "AA STT", "Design Arena", "Arena", "BridgeBench", "Agentset", "MTEB")
for _src in _SOURCES:
    for _fr, _en in BOARD_TASKS_EN.items():
        for _k, _v in ((_fr, _en), (_fr.replace("'", "&#x27;"), _en)):
            PHRASES.setdefault(f"{_src} {_k}", f"{_src} {_v}")
_ORDER = sorted(PHRASES, key=len, reverse=True)
_DECIMAL = re.compile(r"(?<=\d),(?=\d)")
_DATE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4}), (\d{2}:\d{2}) UTC")


def _text(t: str) -> str:
    for fr in _ORDER:
        if fr in t:
            t = t.replace(fr, PHRASES[fr])
    t = _DATE.sub(lambda m: f"{m.group(3)}-{m.group(2)}-{m.group(1)} {m.group(4)} UTC", t)
    return _DECIMAL.sub(".", t)


def _tag(tag: str) -> str:
    tag = re.sub(r'(placeholder|title|aria-label|data-label)="([^"]*)"', lambda m: f'{m.group(1)}="{_text(m.group(2))}"', tag)
    if "data-tip=" in tag:   # chart tooltip JSON: "c":"0,02"
        tag = re.sub(r'(&quot;c&quot;: &quot;)(\d+),(\d+)', r"\1\2.\3", tag)
    return tag


def to_english(html: str) -> str:
    html = html.replace('<html lang="fr">', '<html lang="en">', 1)
    # elements carrying their own English text (generated lists: leaderboards behind a task)
    html = re.sub(r'<div class="bench" data-en="([^"]*)">[^<]*</div>', r'<div class="bench">\1</div>', html)
    html = html.replace('data-lang="fr" class="on"', 'data-lang="fr"').replace('data-lang="en">', 'data-lang="en" class="on">', 1)
    head, sep, rest = html.partition("<script>")
    script, sep2, tail = rest.partition("</script>")
    out, in_style = [], False
    in_raw = False   # <span class="raw">: data quoted as published (sources, e-mails), never translated
    for part in re.split(r"(<[^>]+>)", head):
        if part.startswith("<"):
            in_style = part.startswith("<style") or (in_style and not part.startswith("</style"))
            in_raw = part.startswith('<span class="raw"') or (in_raw and part != "</span>")
            out.append(_tag(part))
        else:
            out.append(part if in_style or in_raw else _text(part))
    for fr, en in sorted(JS.items(), key=lambda kv: -len(kv[0])):
        script = script.replace(fr, en)
    for fr, en in STEPS.items():
        script = script.replace(f"'{fr}'", f"'{en}'")
    script = script.replace("rs.textContent='Cycle running — '+(o.step||'starting')",
                            "rs.textContent='Cycle running — '+(STEPS_EN[o.step]||o.step||'starting')")
    steps_js = "const STEPS_EN=" + __import__("json").dumps(STEPS, ensure_ascii=False) + ";"
    return "".join(out) + sep + steps_js + script + sep2 + tail
