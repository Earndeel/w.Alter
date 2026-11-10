# Walter Memory — Plan de mise en service

> **Walter V1 (Monsieur, 10/11/2026)** : la priorité absolue est la livraison de Walter V1 sur son propre moteur (Walter Engine, base DSH/Cordis appropriée : boucles, sessions, sous-agents, outils et permissions, reprise et contrats appartiennent à Walter). Définition, scénario d'acceptation et tableau de bord : [V1.md](/walter/docs/V1.md) ; architecture du moteur : `/walter/core/engine/docs/02-ARCHITECTURE.md`. Dans ce document, « V1 » désigne Walter Memory V1 (déclarée fonctionnelle le 10/11) ; Memory y garde son rôle : conserver.

> Référence : `ARCHITECTURE.md` (spécification **+ amendements A1–A9**) et `DECISIONS.md` (choix datés).
> Rédigé le 2026-10-01, **validé par Monsieur le 2026-10-01** (D1–D8 tranchées, voir `DECISIONS.md`).
> Révision 2 : intègre A1–A9 ; ajoute la phase **P1.5 Confidentialité** (D5 avant tout import massif).
> Ce plan couvre tout, du socle actuel jusqu'à la mise en service de la V1, puis les évolutions post-V1.
> Les durées sont indicatives et comptées en **jours de travail effectif** (sessions Claude/Hermes + validations
> de Monsieur). Elles seront recalées à la fin de chaque phase.

---

## 0. Cadre

### 0.1 Ce que « mise en service » veut dire

Walter Memory V1 est **en service** quand les six conditions suivantes sont vraies pendant 7 jours consécutifs :

1. **Rien ne se perd** : chaque source branchée a un checkpoint, la réconciliation quotidienne ne trouve aucun
   trou non comblé, et la latence d'ingestion reste sous l'objectif de la source (§8).
2. **Tout est traçable** : chaque fait, préférence, décision ou fiche Kardex remonte à un événement
   canonique, puis à sa source et à son objet original.
3. **Tout est reconstruisible** : un test de rejeu reconstruit Kardex et la mémoire dérivée d'un échantillon depuis
   les événements, avec un résultat équivalent.
4. **Un seul flux** : aucun connecteur n'écrit directement dans Kardex ou Hindsight, et les anciens chemins sont
   coupés.
5. **Walter s'en sert** : Hermes, la voix et Claude obtiennent leur contexte par la même API mémoire, et le
   payload envoyé au modèle est maîtrisé (§P6).
6. **C'est protégé** : les sauvegardes sont chiffrées et copiées hors de la VM, la restauration a été testée, et
   les secrets ont été tournés.

### 0.2 Décisions intégrées (2026-10-01)

- **Conversations Walter (A1, D1)** : chaque message devient un événement `message.received/sent` dans
  `core.events` (session_id, message_id, role, timestamp, texte, reply_to, pièces jointes), avec les métadonnées
  utiles (`tool.called`, `skill.used` : nom, arguments résumés, statut, durée, référence — jamais les gros
  outputs). Les synthèses (`conversation.summarized`) sont dérivées de ces messages. `state.db` reste le stockage
  opérationnel de Hermes ; export brut quotidien JSONL.zst dans le Raw Vault comme copie indépendante.
- **Routeur L2** : mesurer d'abord, en comparant un classifieur local entraîné sur les étiquettes GPT-6 Luna à Jev.
- **Nouveau chantier (P6)** : la mémoire extractive au service du contexte, c'est-à-dire la construction du
  contexte, la compression et la gestion du payload envoyé au modèle.
- Déjà acquis : PG unique + pgvector, Qdrant retiré, Raw Vault sur Drive (en clair), Kardex = social,
  construction par étapes.

### 0.3 Règles de conduite du chantier

- On ne coupe un ancien chemin qu'après une période en parallèle validée (§9 bascule), avec un retour arrière
  écrit.
- Rien n'est supprimé : on isole, on archive ou on désactive. Toute suppression demande l'accord explicite de
  Monsieur.
- Pas de patch dans le cœur de Hermes : on passe par les plugins (memory provider, context engine), les MCP et
  les services externes.
- Chaque phase se termine par une **revue** : démonstration, métriques, mise à jour de `DECISIONS.md` et
  `CLAUDE.md`, et feu vert de Monsieur pour la phase suivante.

---

## 1. Vue d'ensemble

| Phase | Contenu | Durée | Dépend de | Jalon |
|---|---|---|---|---|
| **P0** | Stabilisation et sécurité du socle | 2 j | — | Socle sûr |
| **P1** | Fondation : schémas `core`/`ingestion`/`system`, registre de types, identités source, registre d'objets unique, lib + API, purge break-glass | 4 j | P0 | Journal d'événements opérationnel |
| **P1.5** | Confidentialité (D5) : classes `local_only/redacted_cloud/cloud_allowed`, zone chiffrée du Raw Vault, garde-fou des appels externes | 2 j | P1 | Import massif autorisé |
| **P2** | Connecteurs prioritaires + reprise de l'historique | 6 j | P1.5 | Les bonnes données entrent |
| **P3** | Normalisation + couche de recherche unifiée | 4 j | P2 | Tout est retrouvable |
| **P4** | Entités, graphe temporel, Kardex V1 | 6 j | P3 | Intelligence sociale V1 |
| **P5** | Memory Router L0–L3, adaptateur Hindsight, flux unique | 6 j | P3 (P4 en parallèle) | Mémoire dérivée propre |
| **P6** | Moteur de contexte : extraction, compression, payload | 5 j | P4, P5 | Walter utilise sa mémoire |
| **P7** | Bascule, mise en service, décommissionnement | 3 j + 7 j d'observation | P0–P6 | **V1 en service** |
| **P8** | Modules portables : W.Alter utilisable par n'importe quel runtime (Hermes, Claude Code, Codex, DeepSeek Harness) | continu, par étapes | P6 | Journée sans Hermes |
| P9+ | Consolidation L4/L5, multimodal, nouvelles sources, analytics | continu | V1 | Évolutions |

Total indicatif jusqu'à la V1 : environ **36 jours de travail**, plus 7 jours d'observation. P4 et P5 peuvent se
chevaucher.

```
P0 ─▶ P1 ─▶ P1.5 ─▶ P2 ─▶ P3 ─┬─▶ P4 ─┬─▶ P6 ─▶ P7 (V1)
                              └─▶ P5 ─┘
```

D8 : chaque phase démarre dès que les critères de sortie de la précédente sont validés.

---

## P0 — Stabilisation et sécurité du socle (2 j)

But : ne rien construire sur un socle fragile.

| # | Tâche | Critère de fin |
|---|---|---|
| 0.1 | Finir la classification GPT-6 Luna, puis **isoler** le bruit dans Hindsight : tag `noise:<catégorie>`, exclusion au recall (plugin, walter-voice-memory, walter-core) | Recall propre ; aucun souvenir supprimé ; score autopilot ≥ 95 |
| 0.2 | Sauvegardes **chiffrées (age) et hors VM** : dumps PG et `state.db` vers un dossier Drive séparé « W.Alter Backups » ; restauration testée depuis Drive | Restauration complète réussie depuis la copie distante |
| 0.3 | Tourner le mot de passe PG (`hindsight`) et le mettre dans des EnvironmentFile 0600 ; retirer les mots de passe écrits en dur dans les scripts Kardex | Plus aucun secret dans le code ni dans les unités |
| 0.4 | Reconstruire l'index FTS trigram corrompu de `state.db`, pendant une fenêtre courte avec la gateway arrêtée | `integrity-check` OK |
| 0.5 | Confirmer que la sauvegarde `state.db` v2 tourne (session principale) | Fichier quotidien présent + test de restauration |
| 0.6 | Inventaire des schémas PG (`model_router`, `walter_router`, `x_research`, `user_model`, `memory_facts`) : à garder, à rattacher ou à archiver | Tableau validé par Monsieur |

Bascule à prévoir : aucune. Risque principal : la reconstruction de l'index FTS, à faire pendant une
fenêtre calme.

---

## P1 — Fondation (4 j)

But : la vérité durable a un endroit, un format et une porte d'entrée.

### 1.1 Schémas PostgreSQL (même instance, séparation logique)

- `core.events`, le **journal canonique**, en ajout seul et partitionné par mois :
  `event_id uuid, event_type, type_version, source, source_id, occurred_at, ingested_at, actor_identity_id,
  thread_id, reply_to, content, content_hash, object_refs uuid[], payload jsonb, privacy_class
  (local_only|redacted_cloud|cloud_allowed), epistemic_status (observed|legacy_derived), schema_version`.
  Contrainte d'idempotence : `unique (source, source_id, event_type)`. Ni UPDATE ni DELETE (trigger) : les
  corrections se font par de nouveaux événements (`*.corrected`, `*.retracted`), sauf **break-glass purge** (A9).
- `core.event_types` (A3) : registre extensible `name, version, json_schema, description, status` ; validation
  à l'écriture par la lib/gateway, pas d'enum SQL.
- `core.source_identities` (A4) : acteur tel que la source le connaît (`source, account, external_id,
  display_name, handles/phones`), créé à l'ingestion ; `core.identity_links` (identité → entité, dérivé,
  confiance, provenance) rempli plus tard par la résolution d'entités.
- `core.objects` (A5) : **migration** de `vault.objects`/`vault.links` (schéma `vault` renommé, vue de
  compatibilité pour `rawvault.py`) — un seul registre.
- `core.sources` (comptes et connecteurs : beeper/whatsapp, gmail/lucas…), `core.entities`,
  `core.relationships` (avec `valid_from/valid_to`), `core.provenance` (dérivé → événements/objets).
- `core.derived_items` : données dérivées importées ou produites (faits, synthèses, souvenirs legacy
  Hindsight) avec `status` (`legacy_derived`, `derived`, `verified`), `derived_by`, `processor_version`,
  `model`, `source_event_ids` — **jamais** promues automatiquement en vérité canonique (A2).
- `system.purges` (A9) : procédure `break-glass purge` scriptée (`walter-memory purge --event/--object/--match`),
  qui efface base + Raw Vault + index + Hindsight + **sauvegardes** (réécriture des dumps concernés), et journalise
  qui/quand/pourquoi/empreinte — sans le contenu.
- `ingestion.jobs` (file `FOR UPDATE SKIP LOCKED`, retry avec backoff, dead-letter), `ingestion.checkpoints`
  (`cursor`, `sync_token`, `last_event_id`, `last_ts` par source et par flux), `ingestion.failures`,
  `ingestion.connectors`.
- `system.processors` (nom, version, prompt_hash), `system.model_calls` (modèle, tokens, coût, latence, classe
  de confidentialité), `system.audit_log` (lectures et écritures sensibles).
- Rôles PG séparés : `walter_ingest` (écrit `core`/`ingestion`), `walter_reader` (lecture seule), et
  `hindsight` pour Hindsight uniquement.

### 1.2 Format d'événement v1

Une taxonomie fermée et versionnée (`message.received|sent`, `conversation.summarized`, `email.received|sent`,
`calendar.event`, `file.created`, `photo.taken`, `location.stay`, `tool.called`, `person.met`...), documentée dans
`EVENTS.md`. Chaque type a un validateur (JSON Schema).

### 1.3 Bibliothèque et API

- Package `walter_memory` (`/opt/walter-memory`, son propre venv) : `record_event()`, `put_object()`,
  `get_events()`, `get_object()`, `enqueue()`, `checkpoint()`.
- **Ingestion Gateway** : HTTP sur 127.0.0.1, authentifiée, la seule porte d'écriture pour les connecteurs.
- Exposition dans `walter-core` (MCP) : `memory_get_events`, `memory_get_object`, `memory_record_event`.

### Critères d'acceptation

- Rejouer deux fois le même import crée zéro doublon.
- Un job qui échoue repart sans doublon, et finit en dead-letter après N essais.
- Un benchmark d'insertion à 1 M d'événements synthétiques tient en volume et en latence.
- Les sauvegardes P0 incluent les nouveaux schémas.

---

## P1.5 — Confidentialité (D5, A6) (2 j) — avant tout import massif

- **Classes** : `local_only` (jamais d'API externe, ni LLM ni OCR/STT cloud), `redacted_cloud`
  (pseudonymisation des noms, numéros, e-mails, adresses avant l'appel, réversible localement),
  `cloud_allowed`.
- **Politique** `privacy.policies` : règles par source, compte, contact, type d'événement, type MIME et motif de
  contenu (santé, finances, intime, identifiants, mots de passe/secrets). Le plus restrictif l'emporte. Proposition
  initiale rédigée par Claude, validée par Monsieur.
- **Détection de secrets** à l'ingestion (clés API, mots de passe, OTP, IBAN/CB) → `local_only` et alerte ; ces
  contenus sont candidats à la break-glass purge.
- **Garde-fou** : toute sortie vers un modèle externe passe par une seule fonction (`walter_memory.llm`) qui
  refuse `local_only`, redige `redacted_cloud` et journalise dans `system.model_calls`.
- **Zone chiffrée du Raw Vault** : remote rclone `crypt` (`rawvault-secure:`) dans un sous-dossier Drive séparé,
  clé dans le coffre age + copie hors VM chez Monsieur ; les objets `local_only` y vont, les autres restent en
  clair (choix de Monsieur).
- Critère de sortie : tests (un message « mon code de carte est… » → `local_only` + alerte ; une photo d'un
  contact `local_only` → zone chiffrée ; un appel LLM refusé), politique validée par Monsieur.

---

## P2 — Connecteurs prioritaires et reprise de l'historique (6 j)

But : les bonnes données entrent et aucune ne se perd. Chaque connecteur a un **checkpoint**, une
**réconciliation** quotidienne (« ce que la source a » contre « ce que Walter a ») et une métrique de fraîcheur.

| # | Connecteur | Mode | Contenu | Objectif de fraîcheur |
|---|---|---|---|---|
| 2.1 | **Beeper** (WhatsApp, Instagram, Messenger, Telegram, LINE) | Pull sur l'API Beeper Desktop (Mac, Tailscale), toutes les 2 min | Les 541 conversations : messages, réactions, éditions, suppressions ; médias vers le Raw Vault | < 5 min si le Mac est allumé |
| 2.2 | **Conversations Walter** | Lecture seule de `state.db` (curseur sur l'id de message) | Un événement par message `message.received/sent` (session_id, message_id, role, ts, texte, reply_to, pièces jointes) + `tool.called`/`skill.used` (métadonnées et références, pas les gros outputs) ; **synthèse** dérivée par segment (`conversation.summarized`, L3) | < 5 min (messages), < 15 min (synthèse) |
| 2.3 | **Fichiers envoyés à Walter** | Hook plugin Hermes (pièces jointes) | Raw Vault + `file.created` lié à la session | Immédiat |
| 2.4 | **Reprise de l'historique** | Une seule fois, puis réconciliation | `kardex.messages` (9 238, observés → `core.events`), médias Kardex ; documents et souvenirs Hindsight (1 262 docs, ~33 k unités) + `user_model` → `core.derived_items` en **`legacy_derived`** avec provenance (A2) | — |
| 2.5 | **Gmail + Agenda** | Push Gmail (Pub/Sub) ou historyId en pull ; Calendar en syncToken | E-mails (corps + pièces jointes vers le Raw Vault), événements d'agenda | < 10 min |
| 2.6 | **Export brut des conversations** (si D1 validée) | Quotidien | Sessions `state.db` → JSONL.zst dans le Raw Vault | J+1 |

- Le Beeper (2.1) remplace le webhook `kardex-ingest` (qui perdait 85 % du texte) et rattrape tout l'historique
  depuis le Mac.
- Le Gmail et l'agenda (2.5) demandent une autorisation OAuth de Monsieur (portée `gmail.readonly` et
  `calendar.readonly`).
- Les groupes de discussion entrent comme événements bruts, et leur enrichissement est décidé par le routeur (D4).
- Critère de fin : réconciliation à zéro trou sur 3 jours, et compteurs par source dans le tableau de bord
  autopilot.

---

## P3 — Normalisation et recherche unifiée (4 j)

But : tout est retrouvable par SQL, mots exacts, sens et relations, en pointant vers les mêmes événements.

- **Normalizer (L0)** : langue, fuseau, déduplication inter-sources (même message vu via deux chemins),
  correspondance des comptes vers une identité connue, extraction des URL, numéros, e-mails et dates.
- **`search.chunks`** : découpage des événements textuels (message isolé, fil, e-mail, synthèse de conversation)
  avec FTS multilingue (`simple` + configuration par langue détectée, au lieu du seul français actuel).
- **`search.embeddings`** (pgvector) : banc d'essai sur le jeu de 30 questions étendu à 100 (FR/EN/multi), qui
  compare potion local (déjà en place, gratuit) à un modèle API multilingue. Le choix se fait sur la mesure. Index
  HNSW seulement s'il est validé par le rappel.
- **API de recherche** : `memory.search(query, filters: time/source/person/type)` en hybride (FTS + vecteur +
  filtres SQL, fusion RRF, rerank optionnel) ; `walter-voice-memory` est rebranché dessus.
- Critère de fin : sur le jeu de test, rappel ≥ celui de Hindsight seul, avec une latence p50 < 300 ms (voix
  < 100 ms sans rerank).

---

## P4 — Entités, graphe temporel et Kardex V1 (6 j)

But : savoir qui est qui, comment tout est relié, et rendre Kardex utile.

- **Résolution d'identité** (règles du plan Kardex) : signaux forts (téléphone, e-mail, carte contact,
  correction manuelle) → fusion ; signaux moyens → candidat soumis à Monsieur ; signaux faibles → jamais. Les
  5 829 entités Hindsight sont rapprochées de `core.entities` (les personnes vers Kardex, le reste en
  projets/lieux/orgs), le bruit est isolé.
- **Graphe temporel** : `core.relationships` (knows, works_at, lives_in, member_of...) avec
  `valid_from/valid_to` et provenance.
- **Kardex V1, un consommateur d'événements** (plus aucune écriture directe) :
  - personnes, identités, interactions, groupes, appartenances ;
  - **baselines de relation en L0, sans IA** : messages/jour, latence de réponse, longueur moyenne, ratio
    d'initiation, dernier contact, avec **détection de déviation** sans attribution de cause ;
  - reprise des 361 claims existants avec leur provenance ;
  - conversion des profils psychologiques interprétatifs en **axes observables** (§10 :
    confidence/evidence/sample_size). Les anciens textes sont archivés, pas effacés ;
  - `memory.get_person()` : fiche rapide (identité, relation, préférences, style, changements récents, open
    loops, compteurs de messages/photos/vocaux/documents) avec des règles de mention (`mention_policy`).
- Critère de fin : fiches correctes pour les 20 contacts les plus actifs, validées par Monsieur ; baselines
  calculées pour toutes les relations privées actives en 2026.

---

## P5 — Memory Router, adaptateur Hindsight et flux unique (6 j, en parallèle de P4)

But : l'intelligence coûteuse ne va qu'aux données qui la méritent, et la mémoire dérivée vient d'un seul flux.

- **L0, règles** : ignorer emojis, accusés de réception, doublons, messages système ; classe de confidentialité
  par source et par contact (`local_only` pour les catégories sensibles définies avec Monsieur, D5).
- **L2, bake-off** (décision : mesurer d'abord ; A7) :
  - Candidat A : classifieur local sur embeddings, **amorcé** avec les ~32 800 étiquettes GPT-6 Luna.
  - Candidat B : Jev (`typesafe/jev-router`).
  - **Benchmark indépendant multi-source** (messages Beeper, e-mails, conversations W.Alter, documents), jamais
    vu à l'entraînement, annoté par un modèle fort + échantillon vérifié par Monsieur.
  - **Calibration** des probabilités (Platt/isotonic, ECE mesurée) ; **abstention** sous un seuil de confiance
    → escalade Jev puis L3. On mesure aussi le taux d'abstention et le coût induit.
  - Mesures : précision/rappel par destination, ECE, latence p50/p95, coût pour 1 000 éléments.
- **L3, extracteurs versionnés** : faits, préférences, décisions, open loops, entités/relations, synthèse de
  conversation (cf. 2.2), événements futurs. Chaque sortie porte `derived_by`, `processor_version`, `model`,
  `prompt_hash`, `source_event_ids` et `confidence`.
- **Adaptateur Hindsight** : Hindsight n'est plus alimenté que par le routeur, avec les faits et synthèses
  marqués des `event_id` sources. On coupe `auto_retain` tour par tour dans le plugin (le recall reste) ;
  `kardex-hindsight-sync` est remplacé.
- **Flux unique** : retrait de `user_profile_compiler` (toutes les 5 min, Gemini) ; `USER.md` est compilé
  depuis la mémoire dérivée (job quotidien versionné).
- **Budget** : plafond mensuel d'IA (D6) appliqué par le routeur à partir de `system.model_calls`.
- Critère de fin : sur 7 jours, ≥ 90 % du flux est traité en L0–L2, le coût reste sous le plafond, et aucun
  souvenir nouveau ne tombe dans `infra_internal`/`task_log` (contrôle par échantillonnage).

---

## P6 — Moteur de contexte : extraction, compression, payload (5 j)

But : Walter **utilise** sa mémoire efficacement. C'est la partie extractive qui construit le contexte envoyé au
modèle.

État mesuré (30 derniers jours) : une session desktop envoie en moyenne environ **87 000 tokens par appel**
(30 appels par session, 2,4 M tokens de cache lus). Le recall Hindsight est injecté à chaque tour (600 tokens,
budget `low`). `walter-compress` est actif comme moteur de contexte (compression à 50 % de la fenêtre, cible 10 %).

- **`memory.get_context(query, session, budget)`** assemble un payload **par sections à budgets fixes** :
  1. préfixe stable, compatible avec le cache : identité, règles, profil compilé ;
  2. état courant : projets actifs, open loops, agenda du jour ;
  3. personnes concernées : fiche Kardex courte, seulement si une personne est détectée dans la requête ;
  4. souvenirs pertinents : recherche hybride P3 + Hindsight, dédupliqués ;
  5. résumé de travail de la session (compression).

  Chaque section est tracée (quelles sources, combien de tokens) dans `system.model_calls`.
- **Mémoire extractive de session** : pendant la conversation, extraire au fil de l'eau décisions, contraintes et
  éléments en suspens. Ils nourrissent à la fois la compression (`walter-compress`, garantie de ne pas perdre
  les décisions) et la synthèse PG (2.2).
- **Gestion du payload** :
  - les sorties d'outils volumineuses sont stockées hors contexte, avec un résumé et une référence récupérable
    (`walter_recover`) ;
  - élagage proactif ;
  - plafonds par section ;
  - ordre stable pour maximiser le cache.
- **Intégration sans patch du cœur** : plugin memory provider (prefetch) + plugin context engine
  (`walter-compress`) pour Hermes ; même API pour la voix (budget minuscule, < 1 500 tokens) et pour Claude via
  `walter-core`.
- **Évaluation (A8)** : un jeu de 50 conversations réelles rejouées, mesurant **séparément** : taille réelle du
  contexte, input non caché, cache read, cache write, coût réel, latence (premier token et totale) et qualité des
  réponses (grille de Monsieur + juge LLM).
- Critère de fin : **baisse réelle du coût et de la latence** par tour, sans baisse de qualité significative ;
  la réduction de tokens est un moyen, pas l'objectif (un contexte plus long mais mieux caché peut être meilleur).

---

## P7 — Bascule et mise en service (3 j + 7 j d'observation)

1. **Mode ombre** (dès P2) : les nouveaux chemins tournent à côté des anciens et on compare les compteurs.
2. **Bascule par source**, chacune avec un retour arrière écrit :

   | Ancien chemin | Remplacé par | Retour arrière |
   |---|---|---|
   | webhook `kardex-ingest` + `beeper_watch` sur le Mac | connecteur Beeper (pull) | Réactiver la route webhook |
   | `kardex-hindsight-sync` | adaptateur Hindsight (routeur) | `systemctl enable` |
   | Plugin Hindsight `auto_retain` tour par tour | synthèses + extracteurs | Remettre `auto_retain: true` |
   | `user_profile_compiler` | compilation de `USER.md` depuis la mémoire | Réactiver le timer |
   | Cron `Kardex Semantic Extract` | extracteurs L3 versionnés | Réactiver le cron |
   | `CLAUDE.md` « Hindsight = source de vérité » | Event store + Raw Vault | — |

3. **Observation 7 jours** sur les six conditions du §0.1, avec un rapport quotidien d'autopilot.
4. **Décommissionnement** (avec accord explicite de Monsieur) : Qdrant (conteneur et volume), `memory_facts`,
   `hindsight-pg-old`, services retirés, archivés puis supprimés.
5. **Documentation finale** : `ARCHITECTURE.md`/`DECISIONS.md`/`EVENTS.md`/`RUNBOOK.md` (pannes, restauration,
   rejeu, ajout d'une source).

**Jalon : Walter Memory V1 en service.**

---

## P8 — Modules portables (indépendance du runtime)

Décidé le 2026-10-02 (voir `DECISIONS.md`). Modèle : DeepSeek Harness (« tout est un plugin », journal de
session = source de ce que voit le modèle). Règle : **tout ce qui a un état vit hors de Hermes ; Hermes ne fait
qu'exécuter** (boucle d'agent, fournisseurs de modèles, passerelle Telegram, approbations, sous-agents).

Chaque module Walter (Python, aucun import de Hermes) a trois prises :
1. **adaptateur Hermes** mince (plugin : `register_memory_provider`, `register_context_engine`, middleware
   `llm_request`, `register_secret_source`, hooks) ;
2. **MCP `walter-core`** : outils universels (Claude Code, Codex, DeepSeek Harness, Cursor…) ;
3. **hooks + skills** : comportements automatiques. Les hooks shell de Hermes ont le format Claude Code
   (JSON sur stdin) ; Codex : `notify` (ses hooks sont encore en développement).

| Étape | Contenu | État |
|---|---|---|
| P8.1 | Claude Code et Codex branchés sur le MCP `walter` ; skill passerelle partagée (`/opt/walter-core/skills`) ; `~/.codex/AGENTS.md` = `/root/CLAUDE.md` | fait 2026-10-02 |
| P8.2 | Journal unifié : sessions Claude Code et Codex → `core.events` (connecteur `agent_sessions`, déclenché par les hooks, pas de minuterie) | fait 2026-10-02 |
| P8.3 | Hook de contexte unique (`/opt/walter-core/hooks/walter_hook.py`) : contexte mémoire par message, pointeur de récupération après compaction, compatible Claude Code et hooks shell Hermes | fait 2026-10-02 |
| P8.4 | `walter-context` (`/walter/context`) : décide de ce qui entre dans la fenêtre du modèle ; moteur de compression = sous-module `compress` ; contexte dynamique par fils, sans sessions (voir `CONTEXT-ENGINE.md`) | lot 0 fait 2026-10-21 (walter-compress retiré de Hermes, compresseur natif en attendant le lot 6) ; lots 1-6 planifiés |
| P8.5 | Walter Router branché à l'exécution : passerelle `walter-llm` pour les autres runtimes (fait 2026-10-04) ; middleware Hermes + outil MCP `router_choose` | en partie |
| P8.6 | Walter Memory fournisseur de mémoire natif de Hermes (Hindsight derrière) — lié à P7 | à faire |
| P8.7 | Secrets hors de Hermes : clés des modèles servies depuis Bitwarden par `walter-llm` + jetons par agent (fait 2026-10-04) ; `register_secret_source` Bitwarden pour Hermes ; Walter Router sur Bitwarden ; route abonnement Codex | en partie |
| P8.8 | Profil, skills, projets et tâches planifiées hors de Hermes ; fichier de composition `walter.yaml` (skills → P10 walter-skills) | à faire |
| P8.8b | DeepSeek Harness en banc d'essai (`/opt/dsh`) : MCP, hook, skills, journal, modèle via `walter-llm` — test de bout en bout réussi | fait 2026-10-04 |
| P8.9 | « Journée sans Hermes » : un autre runtime (Claude Code ou DeepSeek Harness) sert Monsieur une journée avec la même mémoire et les mêmes outils | jalon |

Limites assumées : Claude Code et Codex ne laissent remplacer ni leur modèle ni leur compaction ; on les nourrit
(contexte, outils) et on les observe (journal). Les secrets ne leur sont pas ouverts (règle de Monsieur : W.Alter
ou lui seulement).

---

## P9+ — Après la V1 (continu, dans l'ordre de valeur)

1. **Consolidation L5** : quotidienne et hebdomadaire, sur le delta (état précédent + nouveaux événements →
   nouvel état), avec observations et modèles mentaux Hindsight et synthèses de périodes.

(La mémoire procédurale, c'est-à-dire les skills, a sa propre phase : **P10 — walter-skills**, plus bas.)
2. **Enrichissement multimodal (L1)**, avec coût mesuré d'abord sur échantillon :
   - transcription des vocaux, d'abord ceux des messageries ;
   - OCR des captures et documents ;
   - légendes d'images ;
   - embeddings de visages en `local_only`, seulement si Monsieur le valide.
3. **Photothèque** (Takeout ou Photos iCloud sur le Mac) : copie directe `rclone copy` vers le Raw Vault plus
   catalogue (EXIF, GPS).
4. **Localisation** : relancer la collecte (raccourci iOS ou app dédiée), puis clustering, détection des séjours,
   géocodage inverse et `location.stay`. Le prototype de mai est arrêté.
5. **Navigation web** : agent local (extension ou export d'historique), regroupé en sessions de navigation.
6. **Analytics sociales avancées** : communautés, centralité, évolution des groupes, corrélations (L4 justifié
   seulement).
7. **Analyses L4** : évolution comportementale, contradictions, synthèses multi-sources.
8. **Reprocessing** : rejouer l'historique quand un modèle bien meilleur sort, grâce à `processor_version`.


### P9.M — Memory : chantier clos comme fonctionnel (Monsieur, 2026-11-10)
Memory V1 (g1) est en service de bout en bout ; la lecture **g0 + g1** reste la référence (meilleure au banc :
77,2 % contre 63,6 % pour g1 seul, `walter/memory/docs/G0-AVENIR-2026-11.md`). Conservés : les ≈ 4 000
connaissances g1 de la migration `g0mig-1`, ses points de reprise, sauvegardes, migration et retour arrière, les
bancs (`bench/g0_audit.py`, `corpus_v2.py`, `g0_g1.py`, `g0_migrate.py`). **Rien de g0 n'est supprimé.**
Optimisations restantes, chacune mesurée avant adoption, sans refonte générale de Memory :
1. **Quotas dans Walter Router** : le compteur d'abonnement doit refléter aussi la consommation des appels de Memory
   (walter-llm), pas seulement les tours d'agents. À corriger avec les travaux Router.
2. **Vues « sujet » du lot 3 recalculées en double des vues g1** après chaque tour d'agent : à traiter avec Context
   (préflight et fils inter-sessions en sont les lecteurs).
3. Migration des 1 235 fils g0 restants : plus tard, par une méthode économique indépendante des quotas de
   développement Codex / Claude Code (pas de minuteur de reprise sur Codex).
4. Mode de lecture `g1_first` (implémenté, inactif) : remesuré seulement après la fin de la migration.
5. Bruit g0 encore lu en rappel (≈ 5 200) : masquage réversible à mesurer ; archivage de g0 (phase 6a) = décision
   de Monsieur.
6. Triage environnemental toujours en ombre.
---

## P10 — walter-skills : mémoire procédurale hors de Hermes (décidé le 2026-10-09)

Réalise P8.8 pour les skills. Le contexte est dans `DECISIONS.md` (2026-10-09). Entre le 8 septembre et le
3 octobre, le Curator de Hermes a fusionné 193 skills en cascade dans un seul skill générique ; rien n'est perdu
(`~/.hermes/skills/.archive/`).

**Objectif.** Un module Walter qui possède les skills et les workflows : stockage, recherche, apprentissage et
curation. Il est indépendant du runtime : Hermes, Claude Code, Codex, DSH et le futur runtime ne sont que des
clients. Il est **transparent** pour Monsieur, qui n'a aucune commande à taper : le bon skill arrive tout seul
dans le contexte de l'agent. Il doit être **mesurablement meilleur** que Hermes sur le banc (§P10.3).

### P10.1 Architecture

| Couche | Contenu |
|---|---|
| Stock | `/opt/walter-skills` (git = historique et retour arrière), format `SKILL.md` commun à Hermes, Claude Code, Codex et DSH : `skills/<domaine>/<nom>/` (+ `references/`, `scripts/`, `templates/`), `drafts/`, `archive/`. Les workflows sont des skills `type: workflow` (étapes qui appellent d'autres skills). |
| Registre | Postgres `hindsight-pg`, schéma `skills` : catalogue, versions (commit git), état (draft / active / stale / archived), provenance (session, runtime, auteur), liens (`absorbed_into`, `supersedes`, `requires`), fiches de déclenchement, usage, évaluations. |
| Usage | Dérivé de `walter_logs`, pour tous les runtimes (`skill_view` Hermes, `Skill` Claude Code, `skill_read` MCP) ; les lectures du Curator sont exclues. Une ouverture suivie de succès compte plus qu'une ouverture suivie d'une correction de Monsieur. |
| Recherche | Hybride locale : FTS + embeddings `potion-multilingual` sur des **fiches de déclenchement** (10–20 formulations d'intention FR/EN, entités, erreurs typiques, générées hors ligne), à partir du message **et** du tour précédent ; a priori d'usage ; reclassement Cohere rerank-4-fast seulement si c'est ambigu, sans dépasser 700 ms. |
| Injection | Hook unique `walter_hook.py` (Claude Code, Codex, DSH) et adaptateur Hermes : les 2 ou 3 meilleurs skills (nom + une ligne + pourquoi) sont injectés avec le contexte mémoire. Le modèle de l'agent fait le choix final. L'index de 23 k caractères n'est plus envoyé à chaque message. |
| Écriture | Une seule porte : `skill_propose` / `skill_patch` (MCP + plugin Hermes) → `drafts/` avec la preuve (session). Un connecteur récupère ce que Hermes écrit encore dans `~/.hermes/skills`. |
| Prises | Hermes garde son système (skills, index, Curator) : walter-skills le **lit** (synchronisation à sens unique, conflits → `drafts/`), sans `external_dirs` (décision de Monsieur, 2026-10-09). Claude Code / Codex : MCP `walter` + hook. DSH : MCP + hook. Le futur runtime : service :8891. |

### P10.2 Curator Walter (postes du Walter Router, pas de modèle codé en dur)

| Poste | Rôle | Profil |
|---|---|---|
| `skills.indexer` | fiches de déclenchement, descriptions, tags et entités à chaque changement | rapide, peu cher, bon en français |
| `skills.learner` | lit `walter_logs` : procédures répétées, corrections de Monsieur, échecs → brouillons, correctifs, workflows | contexte long, raisonnement, coût moyen |
| `skills.editor` | fusion, réécriture, distillation, réorganisation | modèle de pointe, faible volume |
| `skills.judge` | vérifie qu'une fusion ne perd rien, juge la pertinence (vérité du banc), relance le banc avant d'accepter | **autre famille** que l'éditeur et le chooser (titulaire : Claude Haiku 5.5) |
| `skills.chooser` | choisit, à chaque message, parmi les 40 fiches de la liste courte locale (ou aucune) | rapide (< 1,5 s), peu cher (titulaire : gemini-3.5-flash-lite) |

Garde-fous (leçons du Curator Hermes) :
- pas de fusion en cascade : un skill créé ou modifié par le Curator depuis moins de 30 jours n'est pas absorbable ;
- au plus 5 fusions par passage, et une taille maximale pour un skill de regroupement ;
- fusion sans perte : chaque script, commande, chemin ou identifiant du skill absorbé est soit conservé, soit listé
  comme abandonné avec sa raison, sinon refus ;
- tout changement est un commit git avec sa preuve, et il est annulé automatiquement si le banc régresse ;
- mode fantôme d'abord (branche + rapport) ; ensuite, application automatique des opérations à faible risque
  (format, descriptions, fiches, archivage après plus de 60 jours sans usage réel) et des fusions validées par le juge
  et le banc ; un résumé par semaine sur Telegram ;
- tous les appels de modèles passent par `walter_memory.llm` : `local_only` est exclu de l'apprentissage,
  `redacted_cloud` est masqué, les budgets sont plafonnés.

### P10.3 Banc (`/opt/walter-skills/bench`, fait le 2026-10-09)

Cas réels tirés de `walter_logs` : message de Monsieur (+ tour précédent) → skills que Hermes a ouverts avant le
message suivant. 1 719 cas (1 592 dev < 2026-09-20 ≤ 127 test), 510 skills (229 actifs + archives). Données en 0600,
hors git. Biais connu : la vérité vient des choix de Hermes, qui lisait l'index → le banc avantage la méthode
« LLM + index » ; un sous-ensemble relu par `skills.judge` (vérité v2) le corrigera.

Références (échantillon de 216 cas cloud_allowed, hit@3 = un bon skill parmi les 3 premiers) :

| Méthode | Bibliothèque actuelle (229) | Bibliothèque complète (510) | Latence |
|---|---|---|---|
| MCP `skills_search` actuel (Claude Code/Codex) | 4,6 % | 3,2 % | 2–5 ms |
| BM25 sur l'index Hermes + tour précédent | 34,7 % | 27,3 % | < 1 ms |
| Hybride BM25 + potion + tour précédent | 41,2 % (hit@10 62,5 %) | 25,0 % (hit@10 48,6 %) | 3–7 ms |
| **Hermes : LLM (gpt-6-luna) lisant l'index** | **60,2 %** (hit@1 42,1 %) | **49,1 %** (hit@1 29,2 %) | ~5 s et ~6 k tokens par message |

Cible de bascule : hit@3 ≥ celui de Hermes sur les deux bibliothèques **et** sur la vérité v2, p50 < 500 ms,
aucune régression lors des changements du Curator.

**Résultat (2026-10-09), vérité jugée** (207 cas tenus à l'écart, bibliothèque complète ; « 2 » = le skill à charger) :

| Méthode | top 1 | top 3 | top 5 | Latence p50 | Envoyé au modèle |
|---|---|---|---|---|---|
| Hermes : LLM lisant l'index (+ session) | 72,0 % | 92,3 % | 95,2 % | ~5 s | index ~45 k caractères |
| walter local seul (fusion entraînée sur les jugements) | 50,7 % | 76,8 % | 86,0 % | ~0,1 s | rien |
| walter local + Cohere rerank-4-fast | 48,8 % | 72,5 % | 83,6 % | 0,55 s | 20 fiches |
| **walter local + `skills.chooser` (gemini-3.5-flash-lite) sur 40 fiches** | **77,3 %** | **91,8 %** | 94,2 % | **~1,0 s** | 40 fiches courtes |

Leçons : (1) la vérité « skill que Hermes a ouvert » n'est la bonne réponse que dans 64 % des cas jugés : Hermes
charge par habitude `hermes-agent`, `test-driven-development`, `systematic-debugging`. Entraîner sur ses choix
apprend ses habitudes, donc la fusion est entraînée sur les jugements et l'historique ne sert qu'aux déclencheurs
appris (pondérés par la rareté) et à l'a priori. (2) MiniLM multilingue n'apporte rien par rapport à potion et il
est 4× plus lent. (3) Cohere fait moins bien que le moteur local. (4) Le filtre local « faut-il un skill ? » est
faible (AUC 0,66) ; le chooser, qui peut répondre `[]`, sert de filtre. Coût du chooser : ~0,001 $ par message.
Coût total du banc : ~2,5 $ OpenRouter, plus les juges Haiku (abonnement).
### P10.4 Étapes

| Étape | Contenu | État |
|---|---|---|
| P10.0 | Curator Hermes neutralisé : `consolidate: false`, `prune_builtins: false` | fait 2026-10-09 |
| P10.1 | Banc + références Hermes | fait 2026-10-09 |
| P10.2 | Stock `/opt/walter-skills` : 229 skills synchronisés depuis Hermes (sens unique, Hermes intact, **pas** d'`external_dirs` à la demande de Monsieur) + 63 skills absorbés restaurés (≥ 10 usages) + 218 en `archive/` ; MCP `skills_search`/`skill_read` sur le service (archive exclue par défaut) | fait 2026-10-09 |
| P10.3 | Schéma `skills` (catalog, retrievals, reads, ledger), 510 fiches de déclenchement (`skills.indexer` = gpt-6-luna, 0,33 $), moteur local, service `walter-skills` :8891 | fait 2026-10-09 |
| P10.4 | Injection automatique : hook `walter_hook.py` (Claude Code, dsh) ; Hermes via `pre_llm_call` + plugin `walter-skills` en mode parallèle (2026-10-10) | fait |
| P10.5 | Vérité v2 (`skills.judge` = Claude Haiku 5.5, 647 cas jugés) ; walter ≥ Hermes sur le banc | fait 2026-10-09 |
| P10.6 | Curator Walter actif : archivage des skills morts (60 j sans lecture, jamais jugé utile ; réversible), réparation des références, découpage des SKILL.md trop longs, fusion des doublons (éditeur gpt-6.1-sol via la session Codex de Walter → juge Claude Sonnet 5.5 → contrôle sans perte → contrôle de recherche), workflows qui orchestrent les sous-skills sans les absorber ; **fantôme jusqu'au 2026-10-23** (branche git `curator/<date>`), puis actif ; résumé Telegram le dimanche | en service (fantôme) |
| P10.7 | Apprentissage : écriture `skill_propose`/`skill_patch` + relecture nocturne des brouillons ; jugement automatique des messages récents ; apprenti qui tire des brouillons des sessions ; suggestions sur erreur de commande (fait 2026-10-10) | fait |
| P10.8 | Bascule : Curator Walter actif, Curator Hermes désactivé | jalon |

---

## 8. Exploitation

### 8.1 Supervision (extension de `memory-autopilot`)

- Par source : fraîcheur, volume du jour comparé à la moyenne, trous détectés par la réconciliation, erreurs.
- File : longueur, âge du plus vieux job, dead-letters.
- IA : coût du jour et du mois par niveau L1–L4 comparé au plafond, latences.
- Recherche/contexte : rappel sur le jeu de test (nightly), tokens par appel.
- Alertes Telegram seulement en cas d'anomalie, dans la logique du watchdog actuel.

### 8.2 Sauvegardes (priorités §34)

| Données | Fréquence | Destination | Rétention |
|---|---|---|---|
| `core.events`, `core.provenance`, `core.entities` (PG) | Quotidienne + WAL continu si besoin | Local + Drive chiffré (age) | 7 quotidiennes, 4 hebdomadaires, 12 mensuelles |
| Raw Vault | Déjà hors VM (Drive) | Copie secondaire à décider (D7) | Permanente |
| `state.db` | Quotidienne (v2) | Local + Drive chiffré | 3 locales, 4 hebdomadaires distantes |
| Dérivés (Kardex, Hindsight, search) | Dans le dump PG | — | Reconstruisibles |

Un test de restauration mensuel est automatisé : restauration dans une base de test et comparaison des compteurs.

### 8.3 Sécurité (§33)

- Rôles PG séparés et journal d'audit des lectures sensibles.
- Secrets uniquement en EnvironmentFile 0600 ou dans le coffre age.
- Classe de confidentialité par événement : le routeur applique `local_only` (aucune API externe),
  `redacted_cloud` (pseudonymisation des noms et numéros avant l'appel) ou `cloud_allowed`.
- Raw Vault en clair (choix de Monsieur), avec une **zone chiffrée séparée** à créer pour la catégorie
  `local_only` (D5).

### 8.4 Coûts (ordre de grandeur, à confirmer par mesure)

- L0–L2 : ~0 (local). Une fois le routeur filtrant, le L3 ne touche qu'une petite fraction du flux.
- Reprise de l'historique : coût surtout lié au L3 sur les conversations utiles. Il sera chiffré sur
  échantillon avant lancement.
- Le multimodal est le poste le plus variable (vocaux, photos) : il est toujours chiffré avant d'être lancé.
- Un plafond mensuel (D6) est appliqué automatiquement.

---

## 9. Décisions de Monsieur (tranchées le 2026-10-01)

| # | Décision |
|---|---|
| D1 | Oui : messages individuels W.Alter dans `core.events` + export brut quotidien JSONL.zst dans le Vault |
| D2 | Oui : Gmail et Agenda en lecture seule |
| D3 | `beeper_watch` conservé pendant le shadow mode, retiré après validation |
| D4 | Groupes stockés entièrement en brut, enrichissement sélectif |
| D5 | Catégories `local_only` + zone chiffrée définies **avant P2** (phase P1.5) |
| D6 | Budget IA récurrent séparé du budget exceptionnel backfill/reprocessing (`system.budgets`) |
| D7 | Oui : seconde copie **chiffrée** du Raw Vault |
| D8 | Phases enchaînées dès que leurs critères de sortie sont validés |

## 10. Avancement

| Phase | État | Notes |
|---|---|---|
| P0 | **terminée** (2026-10-01) | voir `DECISIONS.md` (P0 réalisée) et `RUNBOOK.md` |
| P1 | **terminée** (2026-10-01) | lib, CLI, gateway, tests |
| P1.5 | **mécanisme terminé** ; politique D5 à valider | enrichissement cloud suspendu jusqu'à validation |
| P2 | **en cours** | Hermes ✓, historique ✓, Beeper (reprise), Gmail/Agenda (attente OAuth) |
| P3 | **terminée** (2026-10-01) | 28/30 = Hindsight ; voix pas encore rebranchée |
| P4 | **terminée** (2026-10-01) | 1 124 personnes, 97 groupes, mesures Kardex V1 + écarts, `person_lookup` ; fusions par nom en attente de Monsieur |
| P5 | **terminée côté technique** | routeur L0/L2 = filtre, L3 par session (Jev non retenu, bench A7) ; banque Hindsight fantôme alimentée |
| P6 | **en mode fantôme** ; moteur de payload construit | `get_context` + `/v1/context` + `memory_context` ; plugin Hermes `walter_context_mode=shadow` ; métriques A8 collectées ; `walter-context` (projection cache-first) construit et mesuré le 2026-10-11, activation en attente (`CONTEXT-ENGINE.md`) |
| P7 | **à venir** | bascule après ≥ 7 jours de fantôme + décisions D5 / OAuth / clé de récupération |
| Memory V1 (g1) | **fonctionnelle** (2026-11-10) | lecture g0 + g1 ; optimisations restantes : § P9.M |
| P10 | **en service, v2** (2026-10-10 : noyau/ports/boucle, registre Postgres, politique unique, apprentissage implicite, opérateurs ; réactions par le bus Walter, plus de minuterie ni de surveillance de dossiers ; branché sur Hermes, Claude Code, Codex et DSH, testé de bout en bout) | stock 292 + 218 archivés ; service :8891 + MCP + hook ; jugé : walter 77,3 / 91,8 % (top 1 / top 3) contre Hermes 72,0 / 92,3 %, ~1 s contre ~5 s ; Curator en fantôme |
