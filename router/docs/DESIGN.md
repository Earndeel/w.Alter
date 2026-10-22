# Walter Router — conception de bout en bout (v1, 2026-10-04)

> **Le Router ne décide pas quoi penser. Il décide comment Walter doit penser pour cette tâche.**
> Il transforme une requête (ou un événement) en un **plan d'exécution**. Il ne construit pas le contexte détaillé,
> ne rédige pas la réponse et n'exécute pas les outils.

Statut des briques : ✅ en production · 🟡 partiel · 🔜 à construire.

> Ce document décrit la conception et la feuille de route. **L'état actuel du module (organisation, sources, règles,
> accès extérieur) est dans le README** ; les décisions datées sont dans `docs/HISTORY.md`.

---

## 1. Deux horloges

| | **Maintenance** (toutes les 48 h) | **Routage** (à chaque requête / événement) |
|---|---|---|
| But | Décider d'avance *quel modèle pour quel travail* | Comprendre l'intention et appliquer le choix précalculé |
| Qui | Scripts déterministes + **agent économique** (L1 : GPT-6 Luna max via Codex) | **Modèle de décision** (Clef → Mercury Decide → Jev) + lecture de la base |
| Durée | ~15 min | < 1 s (décision ~0,5 s + lecture) |
| Produit | Bibliothèque de modèles, choix par tâche, niveaux texte, dossiers, alertes | ExecutionPlan |

Le modèle de décision ne compare jamais de benchmarks : tout est tranché pendant la maintenance. ✅

---

## 2. Vue d'ensemble

```text
 REQUÊTE (Telegram, app Mac, téléphone)        ÉVÉNEMENT (messages Beeper, mails, agenda…)
              │                                              │
              │                                    INGESTION walter-memory ✅
              │                                    (core.events, Raw Vault, classes de confidentialité)
              │                                              │
              │                                    TRI DES ÉVÉNEMENTS 🔜
              │                                    ignorer / mémoriser / prévenir / préparer / agir
              │                                              │ (si prévenir/préparer/agir)
              ▼                                              ▼
        ┌──────────────── CONTEXT LITE 🟡 ─────────────────────────┐
        │ demande, derniers échanges, sujet, heure, canal, profil   │
        └────────────────────────────┬───────────────────────────────┘
                                     ▼
        ╔══════════════════ WALTER-ROUTER ═════════════════════════╗
        ║ 1. Décision (Clef)        intention → dimensions ✅/🔜    ║
        ║ 2. Règles du propriétaire     favori, rôle, niveau ✅         ║
        ║ 3. Lecture du précalculé  modèle + raisonnement ✅        ║
        ║ 4. Routes d'exécution     Codex → Kie → OpenRouter ✅     ║
        ║ 5. Politique de contexte  profondeur, sources, budget 🔜  ║
        ║ 6. ExecutionPlan          contrat canonique 🟡            ║
        ╚════════════════════════════╤═════════════════════════════╝
                                     ▼
        CONTEXT ENGINE 🟡  (walter-memory, Hindsight, walter-compress, fichiers, web)
                                     ▼
        RUNTIME  R0 outil/direct · R1 tour Hermes · R2 sous-agent · R3 média · R4 interface manuelle
                                     ▼
        RÉPONSE  → TRACE (décision, plan, résultat) → APPRENTISSAGE
```

---

## 3. Entrées

| Entrée | Chemin aujourd'hui | Cible |
|---|---|---|
| Telegram | Gateway Hermes → GPT-6.1 Sol, qui appelle le routeur ensuite 🟡 | Routeur **avant** le modèle (§9) |
| App Mac | Dashboard Hermes, profil `wild` — ingéré en mémoire en `local_only` depuis le 2026-10-04 ✅ | Même chaîne |
| Téléphone | Asterisk → Gemini Live → voice router (Gemini Flash Lite) ✅ | Brancher la décision Clef sur le voice router 🔜 |
| Événements | Ingestion seule, aucune réaction 🟡 | Tri des événements (§10) 🔜 |

---

## 4. Context Lite (ce que voit le modèle de décision)

Quelques centaines de tokens, jamais la mémoire complète : demande, 2–4 derniers échanges résumés, sujet en cours,
projet actif, canal, heure locale, profil (normal / wild), pièces jointes (types, et images pour Clef qui est
multimodal). **Confidentialité** : un contenu `local_only` n'est jamais envoyé à un modèle cloud — pour un événement
`local_only`, la décision se fait sur les métadonnées seules ; `redacted_cloud` passe en version expurgée.

---

## 5. Décision (modèle de décision)

**Chaîne** ✅ : Clef (Cloudflare Workers AI, gratuit ~350/jour) → Mercury Decide (gratuit) → Jev (payant).
Évaluation de référence : `eval/intents_fr.json` (30 demandes) — Clef 30/30 tâches, 6/7 rôles.

**Dimensions v1** (discrètes, versionnées `router_schema = 1`) — les 4 premières existent ✅, les autres 🔜 :

| Dimension | Valeurs |
|---|---|
| `task` | les 25 tâches (texte général, code, front, 3D, vision, document, image, vidéo, voix, musique, météo, calcul, recherche…) |
| `level` | L1 / L2 / L3 (texte général) |
| `video_role` | défaut / premium / action / UGC / budget |
| `unrestricted` | oui / non |
| `strategy` | direct · outil seul · modèle seul · modèle + outils · agent · parallèle |
| `context_depth` | aucun · léger · normal · profond |
| `context_sources` | conversation, mémoire perso, projet, fichiers, web, heure, lieu, agenda (oui/non chacun) |
| `output` | court · détaillé · structuré · code · média |
| `stakes` | faible · normal · élevé (→ confirmation avant action externe) |
| `urgency` | immédiat · normal · peut attendre |
| `confidence` | probabilité du choix de tâche (fournie par le modèle) |

Pas de scores continus « reasoning = 0,91 » : les modèles de décision choisissent bien, ils notent mal.

**Escalade** 🔜 : confiance < 0,35 → l'orchestrateur reçoit le *brief* des rôles et tranche ; toujours ambigu →
Walter demande au propriétaire. **Fast path** 🔜 : « merci », salutations, météo, calcul → R0 sans modèle lourd.

---

## 6. Sélection (lecture du précalculé)

Ordre de priorité ✅ :
1. The owner nomme un modèle → il prime.
2. Contrainte dure (`unrestricted`, poids ouverts) → meilleur modèle qui la respecte.
3. Rôle / favori de la tâche (vidéo par objectif, image = Sunburst, musique = Suno, voix = Gemini TTS).
4. Texte général → **niveau** L1 / L2 / L3 (méthode du propriétaire, `docs/TIERS.md`).
5. Tâche spécialisée → **n°1** du score pondéré multi-benchmarks (pas de n°2/n°3).

Puis **routes d'exécution** ✅ : abonnement Codex → Kie (si disponible et ≤ 1,25 × OpenRouter) → OpenRouter ;
fournisseur en panne au dernier test ou peu fiable dans le journal → relégué ; repli déclaré (L3 → Astra xhigh via
Codex ; tâche spécialisée → meilleur modèle de la tâche accessible par abonnement).

---

## 7. ExecutionPlan v1 — le contrat

```yaml
execution_plan:
  plan_id: …            router_schema: 1          created_at: …
  input:    {channel: telegram, profile: default, request_ref: …}
  decision: {model: cloudflare/clef, task: frontend, level: null, video_role: null, unrestricted: false,
             strategy: model_with_tools, confidence: 0.94, fallback_used: false}
  model:    {model_id: claude-opus-5-5, reasoning: high, why: "n°1 frontend (score pondéré 85)",
             routes: [kie, openrouter], fallback: {model_id: gpt-6-astra, reasoning: max, route: codex}}
  runtime:  {type: subagent}            # direct | tool | hermes_turn | subagent | media | manual_ui
  context:  {depth: normal, budget_tokens: 16000,
             sources: {conversation: high, project_memory: high, personal_memory: low, files: optional,
                       web: false, time: false, location: false, calendar: false}}
  capabilities: {tools: [file, terminal, web], skills: [], workflow: []}
  output:   {format: code, verbosity: detailed}
  guards:   {stakes: normal, confirm_before_external_action: true, max_cost_usd: null, max_seconds: 900}
```

Aujourd'hui `decide` / `route` produisent `decision` + `model` + routes + workflow 🟡 ; le reste est à ajouter 🔜.

---

## 8. Politique de contexte → Context Engine 🔜

Le Router dit **combien et de quel type** ; le Context Engine choisit **quoi exactement**.

| `context_depth` | Conversation | Mémoire projet | Mémoire perso | Fichiers | Budget |
|---|---|---|---|---|---|
| aucun | dernier échange | — | — | — | ~1k |
| léger | 4 derniers échanges | résumé | — | — | ~4k |
| normal | conversation compactée | haute | basse | à la demande | ~16k |
| profond | complète | très haute | moyenne | oui | ~32k+ |

Branchement : `memory_context` de walter-memory (budgets low/mid/high existants) et walter-compress (compaction) ;
heure / lieu / agenda seulement si la dimension le demande.

---

## 9. Runtimes

| Runtime | Quand | Modèle | État |
|---|---|---|---|
| R0 direct / outil | fast path, météo, calcul, agenda | aucun ou L1 pour formuler | 🔜 |
| R1 tour Hermes | conversation courante | **par tour** au sein de Codex (Luna / Sol / Astra) via middleware de plugin ; risque à tester : raisonnement chiffré entre modèles | 🔜 |
| R2 sous-agent | travail texte lourd, autre provider (Opus Kie, GLM Arnict) | modèle choisi, `hermes chat --oneshot` | ✅ `walter_run` |
| R3 média | image, vidéo, musique, voix | favori du rôle, prompt réécrit par L1, workflow | ✅ `walter_generate` |
| R4 interface | Omni 1.1 via Flow (crédits gratuits) | — | 🟡 manuel ; pilotage par computer-use 🔜 |

---

## 10. Événements environnementaux 🟡 (mode observation depuis le 2026-10-04)

Implémenté dans walter-memory : `walter_memory/triage.py`, table `triage.decisions`, règles
`/opt/walter-memory/config/triage_rules.json`, timer `walter-memory-triage` (10 min). Reste : livraison (résumé
Telegram, brouillons de réponse) une fois les règles validées par le propriétaire.


Pour chaque nouvel événement ingéré (message reçu, mail, rendez-vous, photo…), une décision **Clef** sur le
Context Lite de l'événement (métadonnées seules si `local_only`) : `ignorer` · `mémoriser` (déjà fait) ·
`prévenir` the owner · `préparer` (brouillon de réponse, résumé) · `agir` (toujours avec confirmation pour une action
externe). Règles du propriétaire (personnes importantes, sujets, horaires de silence) dans `knowledge.json` ; mêmes
principes que les alertes modèles : jamais de bruit, une ligne claire, numéro court pour répondre.

---

## 11. Maintenance 48 h

1. ✅ Collecte : AA, AA multimodal, Arena (15 classements), Design Arena, BridgeBench, OpenRouter, Kie, Codex, Arnict.
2. ✅ Calcul : identités, offres classées, scores pondérés, n°1 par tâche, niveaux (méthode), dossiers, sondes providers.
3. 🟡 **Agent économique** (Luna max) — aujourd'hui : vérifie et rapproche les noms (`alias-add` validé).
   Cible : il **pilote** la maintenance — relance une source en échec, contourne un site modifié avec Walter Browse,
   enquête sur les nouveaux modèles (annonce officielle, benchmarks annoncés, prix, capacités), et **range** via des
   commandes contrôlées (`alias-add`, `note-model`, `watch-model`, `source-note`) ; jamais les favoris ni la config.
4. 🔜 Données de performance OpenRouter (latence, débit, disponibilité, outils, sortie max) pour ~340 modèles.
5. ✅ Recalcul + notifications **sur changement uniquement**.

---

## 12. Notifications (règle du propriétaire, 2026-10-04) ✅

Seulement ce qui a **changé** depuis le cycle précédent : un **nouveau** modèle qui dépasse un modèle actif ; un
modèle actif **dégradé** ; une **baisse de prix** qui fait entrer un modèle dans la frontière de Pareto. Un bloc par
modèle, rôles groupés. Jamais de comparaison statique, de crédit, de podium ou de rapport.

Mise à jour 2026-10-16 :
- **un message Telegram par nouveauté**, en-tête « W.Alter Router — jj/mm », catégorie du router nommée, prix
  OpenRouter affiché, pas de numéro de référence ;
- **boutons** au lieu de réponses tapées (Bot API, `alerts.send_with_buttons`, rappel `wr:a|d:<alert_id>` traité par le
  plugin Hermes `walter-router`, home chat seulement) : challenger / tier « ✅ Changer » / « ✖️ Garder l'actuel »,
  new_best « ✅ Passer au nouveau » / « ✖️ Garder l'actuel », nerf « 👁️ Masquer », board_down « 👁️ Vu » ;
- un challenger n'est retenu que s'il **bat le modèle en place sur le score global** de la tâche (composite pondéré),
  pas sur un seul classement ;
- **aucun changement de modèle automatique** : un nouveau n°1 est seulement proposé (le modèle en place est épinglé en
  attendant) ; seul le bouton du propriétaire change le favori (`verdict`) ;
- modèles de décision : comparaison Pareto sur 3 axes (AA Decision Index, ms par tâche, coût AA par million de tâches,
  `decision_pareto.py`) et une **recommandation** écrite pour la stack du propriétaire par le modèle L1 à partir de faits
  (`recommend.py`, stockée dans `alerts.evidence.reco`) ;
- une source ou un classement devenu inaccessible → alerte `board_down` (le dernier relevé reste utilisé 21 jours).

---

## 13. Données (PostgreSQL `hindsight-pg`)

- `models` ✅ — bibliothèque : identités, benchmarks, offres, catalogue, choix, dossiers, préférences, fiches,
  affinités, alertes, état des providers, journal d'exécution, retours.
- `router` 🔜 — `dimensions` (versionnées), `decisions` (demande, contexte lite, réponse du modèle de décision),
  `execution_plans`, `outcomes` (réussite, durée, coût, replis, corrections du propriétaire), `corrections` (tâche
  corrigée → mémoire des corrections du modèle de décision), `event_triage`.

---

## 14. Apprentissage

- ✅ Fiabilité réelle (journal) ; ✅ retours du propriétaire (±3 points par note) ; ✅ rapprochements de noms par l'agent.
- 🔜 Mémoire des corrections : une demande proche d'un cas corrigé reprend la correction avant le modèle de décision.
- 🔜 Jeu de test qui grandit avec les vraies demandes corrigées ; l'agent de 48 h réécrit les définitions de tâches
  et ne garde un changement que s'il ne fait pas baisser le score.
- 🔜 (v3) Pareto personnel : coût / réussite réels par région de tâches à partir de `router.outcomes`.

---

## 15. Garde-fous

Secrets jamais affichés (coffre + `.env` 0600 ; Cloudflare via `walter-cloudflare`) ; classes de confidentialité
respectées à chaque étape ; aucune bascule de favori sans le bouton du propriétaire ; action externe = confirmation ; dépenses :
abonnement d'abord, Kie, OpenRouter en dernier.

---

## 16. Feuille de route

| Étape | Contenu | Critère de fin |
|---|---|---|
| **V1 — Plan** | Dimensions v1 dans Clef ; ExecutionPlan complet ; schéma `router` (décisions, plans, résultats) ; fast path ; escalade | 100 % des requêtes routées produisent un plan tracé ; éval ≥ 95 % sur 50 demandes |
| **V2 — Entrée** | Routeur avant le modèle Hermes (middleware, modèle par tour dans Codex, test raisonnement chiffré) ; politique de contexte branchée sur walter-memory | Une demande simple ne passe plus par Sol ; contexte modulé visible dans la trace |
| **V3 — Environnement** | Tri des événements avec règles du propriétaire ; préparation de brouillons | Aucune notification inutile sur une semaine ; The owner valide les règles |
| **V4 — Maintenance pilotée** | Agent Luna chef de maintenance + commandes contrôlées ; données de performance OpenRouter | Nouveau modèle documenté avant son entrée dans les classements |
| **V5 — Pareto personnel** | Mémoire des corrections, jeu de test vivant, coût/réussite réels | Choix ajustés par les résultats réels |

## 17. Décisions ouvertes (à trancher par le propriétaire)

1. Ordre des étapes V1 → V5 (proposition : V1, V2, puis V3 ou V4).
2. Conversations de l'app Mac (profil `wild`) dans la mémoire, en `local_only` : oui / non.
3. Tri des événements : qui compte comme « personne importante », heures de silence, sujets à surveiller.
4. Images reçues / générées : Raw Vault + lien signé temporaire servi par la VM pour Kie (proposé) ou envoi chez Kie.

## Modèle de décision suivi par le cycle (2026-10-14)
AA a publié le **Decision Index v1.0** (2026-10-13) : AA-Omniscience-Decision (précision + non-hallucination, « je ne
sais pas »), HLE-MultiChoice, When2Call (décisions d'appel d'outil), WildGuardTest ; temps et coût par million de tâches.
Source `aa_decision` (page d'évaluation, flux Next.js, sans navigateur) → `models.benchmarks` ; tâche interne
`decision` (interface `decisions`, jamais proposée au classifieur ni aux agents) → meilleur modèle appelable via l'API
Decisions d'OpenRouter, recalculé toutes les 48 h, nouveautés / nerfs notifiés selon les règles habituelles.
`intent.chain()` lit le modèle épinglé (sinon ce meilleur modèle) ; `knowledge.json` `decision.order` : `best_first`
depuis le 2026-10-14 (modèle retenu → Mercury Decide gratuit → Clef sur Workers AI ; aujourd'hui TypeSafe Jev 1.13),
`free_first` possible (Clef → Mercury → meilleur, choix du 2026-10-04). `decision_vision` = même index, modèles qui
lisent les images (aujourd'hui Decider V1.1 27B ; navigation web rapide, tri d'images en masse).

## Page « bibliothèque » (2026-10-14)
https://the instance library domain (host.json library_domain) — `walter-router library` en page web (Cloudflare Pages `walter-library`, Cloudflare
Access : e-mail du propriétaire seulement ; les adresses `*.pages.dev` répondent 404). Republiée en fin de cycle 48 h et
après chaque verdict (`publish-library`).
Bouton « Lancer le cycle complet » : /api/run → the instance control host (host.json control_origin) (Access, jeton de service) →
`walter-router-control` (127.0.0.1:8896, HMAC) → `walter-router-refresh.service`. Refus si un cycle tourne ou a démarré
il y a moins de 10 minutes.

## Abonnements (2026-10-14, révisé le 2026-10-22)
Les abonnements forment la partie `plan/` du module. Depuis le 2026-10-22 ils comptent dans le choix du fournisseur :
un chemin par abonnement passe en premier, au prix de revient d'un token (prix du forfait ÷ valeur API transportée
par mois), tant que son quota hebdomadaire reste sous 90 %. La recherche « abonnements » lit les compteurs, les mails
d'abonnement, le web (SemiAnalysis / Tokenomics, pages des éditeurs, autres mesures) et notifie toute nouveauté sur un
plan du propriétaire. Détails : README, section « How a choice is made » et dossier `plan/`.
