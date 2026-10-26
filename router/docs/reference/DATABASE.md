# Dictionnaire PostgreSQL complet : models

> Généré par `walter-router docs --write`. Modifier les sources, puis régénérer ; ne pas éditer ce fichier.


Types, valeurs par défaut, nullabilité, contraintes et index proviennent du catalogue PostgreSQL. Les JSON de sources et métadonnées sont extensibles : ils ne constituent pas des paramètres typés supplémentaires.

## models.affinities (table)

Close calls: the owner's preferred model inside the tie margin (knowledge.json)

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `model_id` | text | False | — | Identifiant canonique du modèle dans le catalogue du routeur. |
| `scope` | text | False | '*'::text | Portée de la préférence d'affinité ; * représente la portée générale. |
| `weight` | integer | False | 1 | Poids relatif utilisé par le classement ou l'affinité, selon la table. |
| `reason` | text | False | — | Justification de la déclaration ou de la préférence. |
| `declared_at` | timestamp with time zone | False | now() | Horodatage de la déclaration ayant alimenté cette donnée. |

constraints :

```sql
FOREIGN KEY (model_id) REFERENCES models.canonical(model_id)
PRIMARY KEY (model_id, scope)
```

indexes :

```sql
CREATE UNIQUE INDEX affinities_pkey ON models.affinities USING btree (model_id, scope)
```

## models.alerts (table)

challenger, new_best, tier, nerf, pareto, board_down, top3, unranked, billing; evidence (+ stored recommendation evidence.reco), status open/adopted/dismissed. Telegram proposals with buttons; never an automatic switch

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `alert_id` | bigint | False | nextval('models.alerts_alert_id_seq'::regclass) | Identifiant technique de l'alerte. |
| `kind` | text | False | — | Catégorie du fait, de l'alerte ou de l'exécution. |
| `task` | text | False | ''::text | Clé de tâche/poste du routeur, reliée au registre models.tasks. |
| `subject` | text | False | — | Identifiant du sujet auquel l'alerte se rapporte. |
| `evidence` | jsonb | False | '{}'::jsonb | Preuves structurées et recommandation associées à l'alerte ; JSON extensible. |
| `status` | text | False | 'open'::text | État de l'objet (alerte, cycle ou disponibilité selon la table). |
| `first_seen` | timestamp with time zone | False | now() | Première observation de cet objet. |
| `last_seen` | timestamp with time zone | False | now() | Observation la plus récente. |
| `notified_at` | timestamp with time zone | True | — | Date de notification effective ; NULL si non notifiée. |
| `verdict_note` | text | True | — | Commentaire associé à la décision du propriétaire. |
| `role` | text | False | ''::text | Rôle/sous-objectif ; peut aussi porter l'identité du consommateur dans le journal. |
| `ref` | integer | True | — | Référence courte utilisée par les interfaces de décision. |

constraints :

```sql
CHECK ((kind = ANY (ARRAY['challenger'::text, 'unranked'::text, 'source_stale'::text, 'top3'::text, 'billing'::text, 'tier'::text, 'new_best'::text, 'nerf'::text, 'pareto'::text, 'board_down'::text, 'plan_change'::text])))
UNIQUE (kind, task, role, subject)
PRIMARY KEY (alert_id)
CHECK ((status = ANY (ARRAY['baseline'::text, 'open'::text, 'notified'::text, 'dismissed'::text, 'adopted'::text])))
```

indexes :

```sql
CREATE UNIQUE INDEX alerts_kind_task_role_subject_key ON models.alerts USING btree (kind, task, role, subject)
CREATE UNIQUE INDEX alerts_pkey ON models.alerts USING btree (alert_id)
```

## models.aliases (table)

Source name -> model_id per namespace; origin auto / manual (aliases.json, alias-add with evidence) / agent

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `namespace` | text | False | — | Source ou espace de noms de l'identifiant externe. |
| `external_key` | text | False | — | Identifiant original dans la source collectée. |
| `model_id` | text | False | — | Identifiant canonique du modèle dans le catalogue du routeur. |
| `origin` | text | False | — | Origine de la donnée (automatique, déclarée, agent ou source selon la table). |
| `created_at` | timestamp with time zone | False | now() | Date de création de l'enregistrement. |

constraints :

```sql
FOREIGN KEY (model_id) REFERENCES models.canonical(model_id)
CHECK ((origin = ANY (ARRAY['auto'::text, 'manual'::text])))
PRIMARY KEY (namespace, external_key)
```

indexes :

```sql
CREATE UNIQUE INDEX aliases_pkey ON models.aliases USING btree (namespace, external_key)
```

## models.benchmarks (table)

Measured quality per snapshot: benchmark family, task (sub-board), model_id, variant (reasoning level), score (always higher = better), cost (board-published, e.g. AA $ per task), extra (votes, CI, raw measures)

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `snapshot_id` | bigint | False | — | Référence au relevé de source dont provient cette ligne. |
| `benchmark` | text | False | — | Famille du benchmark ; bench_task/task désigne son sous-classement. |
| `task` | text | False | — | Clé de tâche/poste du routeur, reliée au registre models.tasks. |
| `external_key` | text | False | — | Identifiant original dans la source collectée. |
| `model_id` | text | True | — | Identifiant canonique du modèle dans le catalogue du routeur. |
| `variant` | text | False | ''::text | Variante évaluée, notamment effort de réflexion ou résolution. |
| `display_name` | text | True | — | Nom d'affichage, distinct de l'identifiant canonique et de celui du fournisseur. |
| `score` | double precision | False | — | Mesure normalisée dans le sens plus élevé = meilleur ; la valeur brute peut rester dans extra. |
| `score_unit` | text | True | — | Unité du score : index, Elo, pourcentage transformé, etc. |
| `cost` | double precision | True | — | Coût publié par le benchmark ; interpréter avec cost_unit et ne pas inventer un coût par tâche. |
| `cost_unit` | text | True | — | Unité attachée au coût : USD par tâche, par million de tokens ou par unité média. |
| `released` | text | True | — | Date de publication du modèle telle que connue de la source. |
| `extra` | jsonb | False | '{}'::jsonb | Métadonnées du benchmark : votes, caractère provisoire, latence ou mesure brute ; JSON extensible. |

constraints :

```sql
FOREIGN KEY (model_id) REFERENCES models.canonical(model_id)
PRIMARY KEY (snapshot_id, benchmark, task, external_key)
FOREIGN KEY (snapshot_id) REFERENCES models.snapshots(snapshot_id) ON DELETE CASCADE
```

indexes :

```sql
CREATE UNIQUE INDEX benchmarks_pkey ON models.benchmarks USING btree (snapshot_id, benchmark, task, external_key)
CREATE INDEX benchmarks_task ON models.benchmarks USING btree (benchmark, task, score DESC)
```

## models.best_endpoints (vue)

Cheapest usable host per model and usage (interactive: no flex tier; background: flex allowed), 3:1 input:output blend

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `snapshot_id` | bigint | True | — | Référence au relevé de source dont provient cette ligne. |
| `gateway` | text | True | — | Passerelle derrière laquelle cet hébergeur est accessible. |
| `model_id` | text | True | — | Identifiant canonique du modèle dans le catalogue du routeur. |
| `gateway_model` | text | True | — | Identifiant du modèle utilisé par cette passerelle. |
| `host` | text | True | — | Hébergeur effectif derrière une passerelle. |
| `tag` | text | True | — | Identifiant de routage de l'hébergeur. |
| `quantization` | text | True | — | Précision numérique annoncée : bf16, fp8, mxfp4, etc. |
| `price_in_1m` | double precision | True | — | Prix USD par million de tokens d'entrée. |
| `price_out_1m` | double precision | True | — | Prix USD par million de tokens de sortie. |
| `cache_read_1m` | double precision | True | — | Prix USD par million de tokens lus dans le cache, si publié. |
| `context_length` | bigint | True | — | Capacité de contexte annoncée, en tokens ; distincte d'un budget effectif de qualité. |
| `uptime_1d` | double precision | True | — | Taux de réussite/disponibilité sur 24 heures tel que fourni par la source. |
| `uptime_30m` | double precision | True | — | Taux de réussite/disponibilité sur 30 minutes tel que fourni par la source. |
| `status` | integer | True | — | État de l'objet (alerte, cycle ou disponibilité selon la table). |
| `latency_ms` | double precision | True | — | Latence mesurée ou annoncée, en millisecondes. |
| `throughput_tps` | double precision | True | — | Débit annoncé en tokens par seconde. |
| `tools` | boolean | True | — | Prise en charge annoncée des appels d'outils. |
| `structured` | boolean | True | — | Prise en charge annoncée des sorties structurées. |
| `service_tier` | text | True | — | Classe de service de l'hébergeur (flex, standard, priority…). |
| `blended_1m` | double precision | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `vendor_quantization` | text | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `usage` | text | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |

Définition de la vue :

```sql
SELECT DISTINCT ON (model_id, usage) snapshot_id,
    gateway,
    model_id,
    gateway_model,
    host,
    tag,
    quantization,
    price_in_1m,
    price_out_1m,
    cache_read_1m,
    context_length,
    uptime_1d,
    uptime_30m,
    status,
    latency_ms,
    throughput_tps,
    tools,
    structured,
    service_tier,
    blended_1m,
    vendor_quantization,
    usage
   FROM ( SELECT u.snapshot_id,
            u.gateway,
            u.model_id,
            u.gateway_model,
            u.host,
            u.tag,
            u.quantization,
            u.price_in_1m,
            u.price_out_1m,
            u.cache_read_1m,
            u.context_length,
            u.uptime_1d,
            u.uptime_30m,
            u.status,
            u.latency_ms,
            u.throughput_tps,
            u.tools,
            u.structured,
            u.service_tier,
            u.blended_1m,
            u.vendor_quantization,
            'interactive'::text AS usage
           FROM models.usable_endpoints u
          WHERE COALESCE(u.service_tier, ''::text) <> 'flex'::text
        UNION ALL
         SELECT u.snapshot_id,
            u.gateway,
            u.model_id,
            u.gateway_model,
            u.host,
            u.tag,
            u.quantization,
            u.price_in_1m,
            u.price_out_1m,
            u.cache_read_1m,
            u.context_length,
            u.uptime_1d,
            u.uptime_30m,
            u.status,
            u.latency_ms,
            u.throughput_tps,
            u.tools,
            u.structured,
            u.service_tier,
            u.blended_1m,
            u.vendor_quantization,
            'background'::text AS usage
           FROM models.usable_endpoints u) x
  ORDER BY model_id, usage, (uptime_1d IS NULL), blended_1m, uptime_1d DESC NULLS LAST;
```

## models.canonical (table)

One row per model (normalised model_id): vendor, display name, open weights / licence, content_policy (unrestricted + base_model_id), context length

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `model_id` | text | False | — | Identifiant canonique du modèle dans le catalogue du routeur. |
| `vendor` | text | True | — | Éditeur du modèle ou du forfait. |
| `first_seen` | timestamp with time zone | False | now() | Première observation de cet objet. |
| `display_name` | text | True | — | Nom d'affichage, distinct de l'identifiant canonique et de celui du fournisseur. |
| `display_source` | text | True | — | Source du nom d'affichage retenu. |
| `open_weights` | boolean | True | — | Indique si les poids du modèle sont disponibles ; ne signifie pas absence de restrictions. |
| `license` | text | True | — | Licence connue du modèle. |
| `license_source` | text | True | — | Provenance de l'information de licence. |
| `content_policy` | text | False | 'standard'::text | Politique de contenu déclarée, notamment unrestricted lorsqu'établie. |
| `base_model_id` | text | True | — | Modèle de base d'une variante ; permet de tracer les scores hérités. |
| `context_length` | integer | True | — | Capacité de contexte annoncée, en tokens ; distincte d'un budget effectif de qualité. |

constraints :

```sql
CHECK ((content_policy = ANY (ARRAY['standard'::text, 'permissive'::text, 'unrestricted'::text])))
PRIMARY KEY (model_id)
```

indexes :

```sql
CREATE UNIQUE INDEX canonical_pkey ON models.canonical USING btree (model_id)
```

## models.catalog (vue)

One row per model and interface: modes, providers, price range, resolutions, release date, every leaderboard score, open weights, content policy

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `model_id` | text | True | — | Identifiant canonique du modèle dans le catalogue du routeur. |
| `name` | text | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `interface` | text | True | — | Famille d'interface : chat, image, video, audio, music, transcription, embedding, rerank… |
| `modes` | text[] | True | — | Modalités acceptées ou modes de génération (image, video, t2i, i2v…), selon la table. |
| `providers` | text[] | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `price_min` | double precision | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `price_max` | double precision | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `price_unit` | text | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `resolutions` | text[] | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `released` | timestamp with time zone | True | — | Date de publication du modèle telle que connue de la source. |
| `offers` | bigint | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `scores` | jsonb | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `ranked` | boolean | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `open_weights` | boolean | True | — | Indique si les poids du modèle sont disponibles ; ne signifie pas absence de restrictions. |
| `license` | text | True | — | Licence connue du modèle. |
| `content_policy` | text | True | — | Politique de contenu déclarée, notamment unrestricted lorsqu'établie. |
| `base_model_id` | text | True | — | Modèle de base d'une variante ; permet de tracer les scores hérités. |
| `price_in_1m` | double precision | True | — | Prix USD par million de tokens d'entrée. |
| `price_out_1m` | double precision | True | — | Prix USD par million de tokens de sortie. |
| `blended_1m` | double precision | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `token_provider` | text | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `subscriptions` | text[] | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |

Définition de la vue :

```sql
WITH o AS (
         SELECT o.snapshot_id,
            o.provider,
            o.offer_key,
            o.model_id,
            o.interface,
            o.access,
            o.price_in_1m,
            o.price_out_1m,
            o.unit_price,
            o.unit,
            o.provider_created,
            o.pricing,
            o.offer_kind,
            o.modes,
            o.resolution,
            o.audio,
            o.norm_price,
            o.norm_unit
           FROM models.offers o
             JOIN models.latest_snapshots s USING (snapshot_id)
        ), g AS (
         SELECT o.model_id,
            o.interface,
            array_agg(DISTINCT o.provider ORDER BY o.provider) AS providers,
            min(o.norm_price) FILTER (WHERE o.offer_kind = 'generation'::text) AS price_min,
            max(o.norm_price) FILTER (WHERE o.offer_kind = 'generation'::text) AS price_max,
            mode() WITHIN GROUP (ORDER BY o.norm_unit) FILTER (WHERE o.offer_kind = 'generation'::text AND o.norm_price IS NOT NULL) AS price_unit,
            array_agg(DISTINCT o.resolution) FILTER (WHERE o.offer_kind = 'generation'::text AND o.resolution IS NOT NULL) AS resolutions,
            min(o.provider_created) AS released,
            count(*) AS offers
           FROM o
          GROUP BY o.model_id, o.interface
        ), m AS (
         SELECT o.model_id,
            o.interface,
            array_agg(DISTINCT mode.mode ORDER BY mode.mode) AS modes
           FROM o,
            LATERAL unnest(o.modes) mode(mode)
          WHERE o.offer_kind = 'generation'::text
          GROUP BY o.model_id, o.interface
        ), t AS (
         SELECT DISTINCT ON (o.model_id) o.model_id,
            o.provider AS token_provider,
            o.price_in_1m,
            o.price_out_1m,
            (3::double precision * o.price_in_1m + o.price_out_1m) / 4::double precision AS blended_1m
           FROM o
          WHERE o.interface = 'chat'::text AND o.access = 'paid'::text AND o.price_in_1m IS NOT NULL AND o.price_out_1m IS NOT NULL
          ORDER BY o.model_id, ((3::double precision * o.price_in_1m + o.price_out_1m) / 4::double precision)
        ), sub AS (
         SELECT o.model_id,
            array_agg(DISTINCT o.provider) AS subscriptions
           FROM o
          WHERE o.access = ANY (ARRAY['subscription'::text, 'ui'::text])
          GROUP BY o.model_id
        )
 SELECT g.model_id,
    COALESCE(c.display_name, g.model_id) AS name,
    g.interface,
    COALESCE(m.modes, '{}'::text[]) AS modes,
    g.providers,
    g.price_min,
    g.price_max,
    g.price_unit,
    COALESCE(g.resolutions, '{}'::text[]) AS resolutions,
    g.released,
    g.offers,
    COALESCE(b.scores, '{}'::jsonb) AS scores,
    b.scores IS NOT NULL AS ranked,
    c.open_weights,
    c.license,
    c.content_policy,
    c.base_model_id,
        CASE
            WHEN g.interface = 'chat'::text THEN t.price_in_1m
            ELSE NULL::double precision
        END AS price_in_1m,
        CASE
            WHEN g.interface = 'chat'::text THEN t.price_out_1m
            ELSE NULL::double precision
        END AS price_out_1m,
        CASE
            WHEN g.interface = 'chat'::text THEN t.blended_1m
            ELSE NULL::double precision
        END AS blended_1m,
        CASE
            WHEN g.interface = 'chat'::text THEN t.token_provider
            ELSE NULL::text
        END AS token_provider,
    COALESCE(sub.subscriptions, '{}'::text[]) AS subscriptions
   FROM g
     JOIN models.canonical c USING (model_id)
     LEFT JOIN m USING (model_id, interface)
     LEFT JOIN models.model_scores b USING (model_id)
     LEFT JOIN t USING (model_id)
     LEFT JOIN sub USING (model_id);
```

## models.dossiers (table)

Per refresh and task: the JSON the router reads (boards and weights, roles, candidates with per-board evidence, routes, prices, rules)

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `run_id` | bigint | False | — | Identifiant du cycle de calcul ayant produit cette donnée. |
| `task` | text | False | — | Clé de tâche/poste du routeur, reliée au registre models.tasks. |
| `doc` | jsonb | False | — | Dossier de décision structuré : règles, candidats, scores et routes ; JSON extensible. |
| `built_at` | timestamp with time zone | False | now() | Date de construction de la donnée dérivée. |

constraints :

```sql
PRIMARY KEY (run_id, task)
FOREIGN KEY (run_id) REFERENCES models.runs(run_id) ON DELETE CASCADE
FOREIGN KEY (task) REFERENCES models.tasks(task)
```

indexes :

```sql
CREATE UNIQUE INDEX dossiers_pkey ON models.dossiers USING btree (run_id, task)
```

## models.endpoints (table)

Hosts of a model behind a gateway (OpenRouter): price, quantization, reliability, speed, tool / structured-output support. One row per host per snapshot

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `snapshot_id` | bigint | False | — | Référence au relevé de source dont provient cette ligne. |
| `gateway` | text | False | — | Passerelle derrière laquelle cet hébergeur est accessible. |
| `model_id` | text | False | — | Identifiant canonique du modèle dans le catalogue du routeur. |
| `gateway_model` | text | False | — | Identifiant du modèle utilisé par cette passerelle. |
| `host` | text | False | — | Hébergeur effectif derrière une passerelle. |
| `tag` | text | False | — | Identifiant de routage de l'hébergeur. |
| `quantization` | text | True | — | Précision numérique annoncée : bf16, fp8, mxfp4, etc. |
| `price_in_1m` | double precision | True | — | Prix USD par million de tokens d'entrée. |
| `price_out_1m` | double precision | True | — | Prix USD par million de tokens de sortie. |
| `cache_read_1m` | double precision | True | — | Prix USD par million de tokens lus dans le cache, si publié. |
| `context_length` | bigint | True | — | Capacité de contexte annoncée, en tokens ; distincte d'un budget effectif de qualité. |
| `uptime_1d` | double precision | True | — | Taux de réussite/disponibilité sur 24 heures tel que fourni par la source. |
| `uptime_30m` | double precision | True | — | Taux de réussite/disponibilité sur 30 minutes tel que fourni par la source. |
| `status` | integer | True | — | État de l'objet (alerte, cycle ou disponibilité selon la table). |
| `latency_ms` | double precision | True | — | Latence mesurée ou annoncée, en millisecondes. |
| `throughput_tps` | double precision | True | — | Débit annoncé en tokens par seconde. |
| `tools` | boolean | True | — | Prise en charge annoncée des appels d'outils. |
| `structured` | boolean | True | — | Prise en charge annoncée des sorties structurées. |
| `service_tier` | text | True | — | Classe de service de l'hébergeur (flex, standard, priority…). |

constraints :

```sql
PRIMARY KEY (snapshot_id, gateway, gateway_model, tag)
FOREIGN KEY (snapshot_id) REFERENCES models.snapshots(snapshot_id) ON DELETE CASCADE
```

indexes :

```sql
CREATE INDEX endpoints_model ON models.endpoints USING btree (model_id)
CREATE UNIQUE INDEX endpoints_pkey ON models.endpoints USING btree (snapshot_id, gateway, gateway_model, tag)
```

## models.exec_log (table)

Every routed execution attempt (walter_run, generate, walter-llm): provider, model, ok, seconds, cost. >= 50 % failures over >= 3 runs in 14 days demotes the route

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `exec_id` | bigint | False | nextval('models.exec_log_exec_id_seq'::regclass) | Identifiant d'une tentative physique d'exécution. |
| `at` | timestamp with time zone | False | now() | Horodatage du fait enregistré. |
| `task` | text | True | — | Clé de tâche/poste du routeur, reliée au registre models.tasks. |
| `role` | text | True | — | Rôle/sous-objectif ; peut aussi porter l'identité du consommateur dans le journal. |
| `model_id` | text | True | — | Identifiant canonique du modèle dans le catalogue du routeur. |
| `provider` | text | True | — | Fournisseur/passerelle ; distinct de l'hébergeur et du modèle. |
| `model` | text | True | — | Identifiant natif demandé au fournisseur, distinct du model_id canonique. |
| `ok` | boolean | False | — | Résultat de la tentative ou du contrôle ; ne prouve pas à lui seul une facturation fournisseur. |
| `skipped` | text | True | — | Motif d'une tentative écartée sans exécution, si applicable. |
| `seconds` | real | True | — | Durée en secondes. |
| `cost_usd` | real | True | — | Coût USD connu ; NULL signifie inconnu, pas gratuit. |
| `fallback_for` | text | True | — | Référence historique du modèle remplacé ; aucune substitution automatique dans le texte actuel. |
| `kind` | text | False | 'text'::text | Catégorie du fait, de l'alerte ou de l'exécution. |

constraints :

```sql
PRIMARY KEY (exec_id)
```

indexes :

```sql
CREATE UNIQUE INDEX exec_log_pkey ON models.exec_log USING btree (exec_id)
CREATE INDEX exec_log_recent ON models.exec_log USING btree (provider, model_id, at DESC)
```

## models.feedback (table)

the owner's verdicts on a model (-2..2), +/-3 composite points each, capped +/-9

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `feedback_id` | bigint | False | nextval('models.feedback_feedback_id_seq'::regclass) | Identifiant du retour utilisateur. |
| `at` | timestamp with time zone | False | now() | Horodatage du fait enregistré. |
| `model_id` | text | False | — | Identifiant canonique du modèle dans le catalogue du routeur. |
| `task` | text | True | — | Clé de tâche/poste du routeur, reliée au registre models.tasks. |
| `rating` | integer | False | — | Évaluation du propriétaire, de -2 à +2. |
| `note` | text | True | — | Explication ou précision attachée à la donnée. |
| `source` | text | False | 'owner'::text | Provenance ou méthode de mesure ; ce champ n'est pas une preuve d'exécution à lui seul. |

constraints :

```sql
FOREIGN KEY (model_id) REFERENCES models.canonical(model_id)
PRIMARY KEY (feedback_id)
CHECK (((rating >= '-2'::integer) AND (rating <= 2)))
```

indexes :

```sql
CREATE UNIQUE INDEX feedback_pkey ON models.feedback USING btree (feedback_id)
```

## models.guardian_incidents (table)

Maintenance incidents of the Walter Router seen by its guardian (guardian/): detection, repair attempts, outcome.

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `incident_id` | bigint | False | nextval('models.guardian_incidents_incident_id_seq'::regclass) | Incident number. |
| `key` | text | False | — | Stable identity of the problem (source:aa_stt, provider:kie, test:<pytest node id>, cycle): one open row per key. |
| `kind` | text | False | — | source_stale \| source_error \| provider_down \| test_failure \| cycle_failed. |
| `subject` | text | False | — | What is affected: source kind, provider, test node id or run. |
| `status` | text | False | 'open'::text | open (seen, not handled yet) \| repairing \| fixed (patch applied and verified) \| external (cause outside the module: provider or site outage, waiting) \| needs_owner (a decision only the owner can take) \| deferred (verified patch waiting for files another session is editing) \| resolved (gone by itself). |
| `opened_at` | timestamp with time zone | False | now() | First detection. |
| `last_seen_at` | timestamp with time zone | False | now() | Last check that still saw the problem. |
| `closed_at` | timestamp with time zone | True | — | When it was fixed or went away; null while open. |
| `attempts` | integer | False | 0 | Repair agent runs spent on this incident. |
| `last_attempt_at` | timestamp with time zone | True | — | Last repair agent run. |
| `detail` | jsonb | False | '{}'::jsonb | Evidence of the detection (age, error, probe answer, test output). |
| `verdict` | jsonb | True | — | Last repair verdict: agent outcome, cause, changed files, gate results, commit, deferred patch. |
| `notified_at` | timestamp with time zone | True | — | When the owner was told (once per incident outcome). |

constraints :

```sql
PRIMARY KEY (incident_id)
```

indexes :

```sql
CREATE UNIQUE INDEX guardian_incidents_one_open ON models.guardian_incidents USING btree (key) WHERE (closed_at IS NULL)
CREATE UNIQUE INDEX guardian_incidents_pkey ON models.guardian_incidents USING btree (incident_id)
```

## models.latest_dossiers (vue)

Dossier of each task from the latest run

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `task` | text | True | — | Clé de tâche/poste du routeur, reliée au registre models.tasks. |
| `doc` | jsonb | True | — | Dossier de décision structuré : règles, candidats, scores et routes ; JSON extensible. |
| `built_at` | timestamp with time zone | True | — | Date de construction de la donnée dérivée. |

Définition de la vue :

```sql
SELECT d.task,
    d.doc,
    d.built_at
   FROM models.dossiers d
     JOIN models.latest_run r USING (run_id);
```

## models.latest_run (vue)

Latest successful refresh run id

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `run_id` | bigint | True | — | Identifiant du cycle de calcul ayant produit cette donnée. |

Définition de la vue :

```sql
SELECT run_id
   FROM models.runs
  WHERE status = 'ok'::text
  ORDER BY run_id DESC
 LIMIT 1;
```

## models.latest_snapshots (vue)

Latest snapshot id per source kind

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `kind` | text | True | — | Catégorie du fait, de l'alerte ou de l'exécution. |
| `snapshot_id` | bigint | True | — | Référence au relevé de source dont provient cette ligne. |
| `fetched_at` | timestamp with time zone | True | — | Date de collecte de la source. |

Définition de la vue :

```sql
SELECT DISTINCT ON (kind) kind,
    snapshot_id,
    fetched_at
   FROM models.snapshots
  ORDER BY kind, fetched_at DESC, snapshot_id DESC;
```

## models.latest_subscription_costs (vue)

Latest cost price per subscription

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `sub_id` | text | True | — | Identifiant du forfait dans les déclarations de l'instance. |
| `at` | timestamp with time zone | True | — | Horodatage du fait enregistré. |
| `price_usd_month` | double precision | True | — | Montant mensuel du forfait, en USD. |
| `api_value_month_pace` | double precision | True | — | Valeur API équivalente extrapolée au rythme d'usage observé sur un mois. |
| `api_value_month_full` | double precision | True | — | Valeur API équivalente estimée à capacité complète sur un mois. |
| `ratio_pace` | double precision | True | — | Prix mensuel divisé par valeur API équivalente au rythme observé ; ratio, pas pourcentage. |
| `ratio_full` | double precision | True | — | Prix mensuel divisé par valeur API équivalente à pleine capacité ; ratio. |
| `used_percent` | double precision | True | — | Quota consommé, en pourcentage 0..100, observé ou estimé selon la source. |
| `detail` | jsonb | True | — | Détails structurés de la mesure ou du contrôle ; JSON extensible. |

Définition de la vue :

```sql
SELECT DISTINCT ON (sub_id) sub_id,
    at,
    price_usd_month,
    api_value_month_pace,
    api_value_month_full,
    ratio_pace,
    ratio_full,
    used_percent,
    detail
   FROM models.subscription_costs
  ORDER BY sub_id, at DESC;
```

## models.latest_subscription_usage (vue)

Latest quota reading per subscription and window

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `reading_id` | bigint | True | — | Identifiant d'un relevé de quota. |
| `sub_id` | text | True | — | Identifiant du forfait dans les déclarations de l'instance. |
| `read_at` | timestamp with time zone | True | — | Date du relevé. |
| `window_name` | text | True | — | Fenêtre du quota (weekly, fenêtre courte, etc.). |
| `used_percent` | numeric(6,2) | True | — | Quota consommé, en pourcentage 0..100, observé ou estimé selon la source. |
| `resets_at` | timestamp with time zone | True | — | Date annoncée de réinitialisation du quota. |
| `source` | text | True | — | Provenance ou méthode de mesure ; ce champ n'est pas une preuve d'exécution à lui seul. |
| `estimated` | boolean | True | — | Indique une estimation ; ne pas la présenter comme une mesure directe. |
| `detail` | jsonb | True | — | Détails structurés de la mesure ou du contrôle ; JSON extensible. |

Définition de la vue :

```sql
SELECT DISTINCT ON (sub_id, window_name) reading_id,
    sub_id,
    read_at,
    window_name,
    used_percent,
    resets_at,
    source,
    estimated,
    detail
   FROM models.subscription_usage
  ORDER BY sub_id, window_name, read_at DESC;
```

## models.model_scores (vue)

All latest scores of a model as one JSON (benchmark:task -> score)

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `model_id` | text | True | — | Identifiant canonique du modèle dans le catalogue du routeur. |
| `scores` | jsonb | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |

Définition de la vue :

```sql
SELECT model_id,
    jsonb_object_agg((benchmark || ':'::text) || task, score) AS scores
   FROM ( SELECT b.model_id,
            b.benchmark,
            b.task,
            max(b.score) AS score
           FROM models.benchmarks b
             JOIN models.latest_snapshots s USING (snapshot_id)
          GROUP BY b.model_id, b.benchmark, b.task) x
  GROUP BY model_id;
```

## models.offers (table)

Callable, priced offers per snapshot: provider, interface, access (paid/subscription/ui/free), $/M tokens or unit price, media modes/resolution/audio, normalised price (per second, image, 1000 chars, minute)

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `snapshot_id` | bigint | False | — | Référence au relevé de source dont provient cette ligne. |
| `provider` | text | False | — | Fournisseur/passerelle ; distinct de l'hébergeur et du modèle. |
| `offer_key` | text | False | — | Identifiant de l'offre chez son fournisseur. |
| `model_id` | text | True | — | Identifiant canonique du modèle dans le catalogue du routeur. |
| `interface` | text | False | — | Famille d'interface : chat, image, video, audio, music, transcription, embedding, rerank… |
| `access` | text | False | — | Mode d'accès annoncé : paid, subscription, free ou ui. |
| `price_in_1m` | double precision | True | — | Prix USD par million de tokens d'entrée. |
| `price_out_1m` | double precision | True | — | Prix USD par million de tokens de sortie. |
| `unit_price` | double precision | True | — | Prix unitaire USD publié, à interpréter avec unit. |
| `unit` | text | True | — | Unité de la valeur/prix concerné (image, seconde, minute, etc.). |
| `provider_created` | timestamp with time zone | True | — | Date de création/publication de l'offre chez le fournisseur. |
| `pricing` | jsonb | False | '{}'::jsonb | Détails tarifaires et de transport de la source ; JSON extensible, sans secret. |
| `offer_kind` | text | False | 'generation'::text | Classification de l'offre média. |
| `modes` | text[] | False | '{}'::text[] | What the offer does or reads besides text: media generation modes (t2v, i2v, r2v, v2v, t2i, i2i); for chat and decision offers the inputs the model accepts (image, audio, video, file — from OpenRouter's input_modalities). |
| `resolution` | text | True | — | Résolution annoncée pour l'offre média. |
| `audio` | boolean | True | — | Capacité audio annoncée pour l'offre. |
| `norm_price` | double precision | True | — | Prix unitaire normalisé pour comparer des offres à unité égale. |
| `norm_unit` | text | True | — | Unité du prix normalisé, par exemple USD par seconde de vidéo. |

constraints :

```sql
CHECK ((access = ANY (ARRAY['paid'::text, 'subscription'::text, 'free'::text, 'ui'::text])))
FOREIGN KEY (model_id) REFERENCES models.canonical(model_id)
CHECK ((offer_kind = ANY (ARRAY['generation'::text, 'fee'::text, 'tool'::text])))
PRIMARY KEY (snapshot_id, provider, offer_key)
FOREIGN KEY (snapshot_id) REFERENCES models.snapshots(snapshot_id) ON DELETE CASCADE
```

indexes :

```sql
CREATE INDEX offers_model ON models.offers USING btree (model_id)
CREATE UNIQUE INDEX offers_pkey ON models.offers USING btree (snapshot_id, provider, offer_key)
```

## models.open_models (vue)

Open-weight and unrestricted models, scores inherited from the base model flagged

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `model_id` | text | True | — | Identifiant canonique du modèle dans le catalogue du routeur. |
| `name` | text | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `interface` | text | True | — | Famille d'interface : chat, image, video, audio, music, transcription, embedding, rerank… |
| `modes` | text[] | True | — | Modalités acceptées ou modes de génération (image, video, t2i, i2v…), selon la table. |
| `providers` | text[] | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `price_min` | double precision | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `price_max` | double precision | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `price_unit` | text | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `resolutions` | text[] | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `released` | timestamp with time zone | True | — | Date de publication du modèle telle que connue de la source. |
| `offers` | bigint | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `scores` | jsonb | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `ranked` | boolean | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `open_weights` | boolean | True | — | Indique si les poids du modèle sont disponibles ; ne signifie pas absence de restrictions. |
| `license` | text | True | — | Licence connue du modèle. |
| `content_policy` | text | True | — | Politique de contenu déclarée, notamment unrestricted lorsqu'établie. |
| `base_model_id` | text | True | — | Modèle de base d'une variante ; permet de tracer les scores hérités. |
| `scores_or_base` | jsonb | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `score_from_base` | boolean | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |

Définition de la vue :

```sql
SELECT k.model_id,
    k.name,
    k.interface,
    k.modes,
    k.providers,
    k.price_min,
    k.price_max,
    k.price_unit,
    k.resolutions,
    k.released,
    k.offers,
    k.scores,
    k.ranked,
    k.open_weights,
    k.license,
    k.content_policy,
    k.base_model_id,
    COALESCE(NULLIF(k.scores, '{}'::jsonb), bb.scores, '{}'::jsonb) AS scores_or_base,
    k.scores = '{}'::jsonb AND bb.scores IS NOT NULL AS score_from_base
   FROM models.catalog k
     LEFT JOIN models.model_scores bb ON bb.model_id = k.base_model_id
  WHERE k.open_weights OR k.content_policy = 'unrestricted'::text;
```

## models.plan_evidence (table)

Facts about subscription plans with their source: value of a plan at API prices, tokens or messages per window, price, limits, changes (web research, billing e-mails, owner, our measures)

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `evidence_id` | bigint | False | nextval('models.plan_evidence_evidence_id_seq'::regclass) | Identifiant d'une preuve concernant un abonnement. |
| `sub_id` | text | True | — | Identifiant du forfait dans les déclarations de l'instance. |
| `vendor` | text | False | — | Éditeur du modèle ou du forfait. |
| `plan` | text | False | — | Nom du forfait. |
| `model_id` | text | True | — | Identifiant canonique du modèle dans le catalogue du routeur. |
| `metric` | text | False | — | Nom de la mesure étayée par la preuve. |
| `value` | double precision | True | — | Valeur observée/déclarée, à interpréter avec metric et unit. |
| `unit` | text | True | — | Unité de la valeur/prix concerné (image, seconde, minute, etc.). |
| `source_name` | text | False | — | Nom de la source de la preuve. |
| `source_url` | text | True | — | URL de provenance, sans secret. |
| `published` | date | True | — | Date de publication de la preuve. |
| `quote` | text | True | — | Extrait justificatif de la source. |
| `origin` | text | False | — | Origine de la donnée (automatique, déclarée, agent ou source selon la table). |
| `found_at` | timestamp with time zone | False | now() | Date de découverte de la preuve. |

constraints :

```sql
CHECK ((metric = ANY (ARRAY['usd_value_month'::text, 'tokens_month'::text, 'messages_5h'::text, 'messages_week'::text, 'price_usd_month'::text, 'limit_note'::text, 'plan_change'::text])))
CHECK ((origin = ANY (ARRAY['web'::text, 'email'::text, 'owner'::text, 'measure'::text])))
PRIMARY KEY (evidence_id)
UNIQUE (sub_id, model_id, metric, source_url, value)
```

indexes :

```sql
CREATE UNIQUE INDEX plan_evidence_pkey ON models.plan_evidence USING btree (evidence_id)
CREATE UNIQUE INDEX plan_evidence_sub_id_model_id_metric_source_url_value_key ON models.plan_evidence USING btree (sub_id, model_id, metric, source_url, value)
```

## models.preferences (table)

the owner's choices per task / role: objective, pinned model/variant/provider, role label, description and signals, watch. A change of favourite only through their verdict

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `task` | text | False | — | Clé de tâche/poste du routeur, reliée au registre models.tasks. |
| `objective` | text | True | — | Objectif déclaré de sélection, notamment best_available, value ou level. |
| `pinned_model_id` | text | True | — | Modèle favori explicitement déclaré ; prime sur un challenger calculé. |
| `pinned_variant` | text | False | ''::text | Variante de réflexion/rendu imposée avec le favori. |
| `pinned_provider` | text | True | — | Fournisseur déclaré avec le favori. |
| `note` | text | True | — | Explication ou précision attachée à la donnée. |
| `declared_at` | timestamp with time zone | False | now() | Horodatage de la déclaration ayant alimenté cette donnée. |
| `role` | text | False | 'default'::text | Rôle/sous-objectif ; peut aussi porter l'identité du consommateur dans le journal. |
| `watch` | text | False | 'quality'::text | Politique de surveillance du favori : quality, dominance ou none. |
| `label` | text | True | — | Libellé lisible de la tâche ou du rôle. |
| `description` | text | True | — | Description fonctionnelle. |
| `signals` | text[] | False | '{}'::text[] | Indices textuels aidant à reconnaître un rôle/objectif. |
| `priority` | integer | False | 0 | Priorité relative d'un rôle lors de sa sélection. |

constraints :

```sql
CHECK ((objective = ANY (ARRAY['value'::text, 'best_available'::text])))
FOREIGN KEY (pinned_model_id) REFERENCES models.canonical(model_id)
PRIMARY KEY (task, role)
FOREIGN KEY (task) REFERENCES models.tasks(task)
CHECK ((watch = ANY (ARRAY['quality'::text, 'dominance'::text, 'none'::text])))
```

indexes :

```sql
CREATE UNIQUE INDEX preferences_pkey ON models.preferences USING btree (task, role)
```

## models.profiles (table)

What a model is for (knowledge.json): strengths, weaknesses, workflow, effort, access and cost notes

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `model_id` | text | False | — | Identifiant canonique du modèle dans le catalogue du routeur. |
| `strengths` | text[] | False | '{}'::text[] | Forces déclarées du modèle. |
| `weaknesses` | text[] | False | '{}'::text[] | Limites déclarées du modèle. |
| `workflow` | jsonb | False | '[]'::jsonb | Étapes/conseils d'usage déclarés pour ce modèle. |
| `effort` | text | True | — | Mode d'accompagnement déclaré ; distinct du niveau de raisonnement demandé au fournisseur. |
| `access_note` | text | True | — | Précisions d'accès au modèle. |
| `cost_note` | text | True | — | Précisions sur son coût. |
| `content_policy` | text | True | — | Politique de contenu déclarée, notamment unrestricted lorsqu'établie. |
| `note` | text | True | — | Explication ou précision attachée à la donnée. |
| `source` | text | False | 'owner'::text | Provenance ou méthode de mesure ; ce champ n'est pas une preuve d'exécution à lui seul. |
| `declared_at` | timestamp with time zone | False | now() | Horodatage de la déclaration ayant alimenté cette donnée. |

constraints :

```sql
CHECK ((content_policy = ANY (ARRAY['standard'::text, 'permissive'::text, 'unrestricted'::text])))
CHECK ((effort = ANY (ARRAY['direct'::text, 'guided'::text, 'workflow'::text])))
FOREIGN KEY (model_id) REFERENCES models.canonical(model_id)
PRIMARY KEY (model_id)
```

indexes :

```sql
CREATE UNIQUE INDEX profiles_pkey ON models.profiles USING btree (model_id)
```

## models.provider_status (table)

Last live 5-token probe per provider (OpenRouter credit in detail); a failed provider goes last in routes

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `provider` | text | False | — | Fournisseur/passerelle ; distinct de l'hébergeur et du modèle. |
| `ok` | boolean | False | — | Résultat de la tentative ou du contrôle ; ne prouve pas à lui seul une facturation fournisseur. |
| `checked_at` | timestamp with time zone | False | now() | Date du dernier contrôle de disponibilité. |
| `latency_ms` | integer | True | — | Latence mesurée ou annoncée, en millisecondes. |
| `detail` | text | True | — | Détails structurés de la mesure ou du contrôle ; JSON extensible. |

constraints :

```sql
PRIMARY KEY (provider)
```

indexes :

```sql
CREATE UNIQUE INDEX provider_status_pkey ON models.provider_status USING btree (provider)
```

## models.runs (table)

One row per refresh: status and summary (sources, changes, alerts, notifications)

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `run_id` | bigint | False | nextval('models.runs_run_id_seq'::regclass) | Identifiant du cycle de calcul ayant produit cette donnée. |
| `started_at` | timestamp with time zone | False | now() | Début du cycle. |
| `finished_at` | timestamp with time zone | True | — | Fin du cycle. |
| `status` | text | False | 'running'::text | État de l'objet (alerte, cycle ou disponibilité selon la table). |
| `summary` | jsonb | False | '{}'::jsonb | Résumé structuré du cycle : collectes, changements et alertes ; JSON extensible. |

constraints :

```sql
PRIMARY KEY (run_id)
CHECK ((status = ANY (ARRAY['running'::text, 'ok'::text, 'failed'::text])))
```

indexes :

```sql
CREATE UNIQUE INDEX runs_pkey ON models.runs USING btree (run_id)
```

## models.schema_migrations (table)

Applied migrations of /opt/walter-router/migrations

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `version` | text | False | — | Identifiant de migration appliquée. |
| `applied_at` | timestamp with time zone | False | now() | Date d'application de la migration. |

constraints :

```sql
PRIMARY KEY (version)
```

indexes :

```sql
CREATE UNIQUE INDEX schema_migrations_pkey ON models.schema_migrations USING btree (version)
```

## models.selection (table)

Per refresh, task, level (best, value, L1-L3, frontier...) and rank: chosen model, variant, quality, real cost, provider, offer, subscription, reasons

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `run_id` | bigint | False | — | Identifiant du cycle de calcul ayant produit cette donnée. |
| `task` | text | False | — | Clé de tâche/poste du routeur, reliée au registre models.tasks. |
| `level` | text | False | — | Niveau de sélection (best, value, L1/L2/L3, frontier…), selon le contexte. |
| `rank` | integer | False | — | Rang calculé, 1 étant le premier. |
| `model_id` | text | False | — | Identifiant canonique du modèle dans le catalogue du routeur. |
| `variant` | text | False | ''::text | Variante évaluée, notamment effort de réflexion ou résolution. |
| `display_name` | text | True | — | Nom d'affichage, distinct de l'identifiant canonique et de celui du fournisseur. |
| `quality` | double precision | True | — | Score on the task quality unit; null = newer version not yet ranked on this board (predecessor score in reasons.measured_quality) |
| `quality_unit` | text | True | — | Unité de qualité calculée. |
| `real_cost` | double precision | True | — | Coût de comparaison retenu par l'analyse ; interpréter avec cost_unit. |
| `cost_unit` | text | True | — | Unité attachée au coût : USD par tâche, par million de tokens ou par unité média. |
| `provider` | text | True | — | Fournisseur/passerelle ; distinct de l'hébergeur et du modèle. |
| `offer_key` | text | True | — | Identifiant de l'offre chez son fournisseur. |
| `subscription` | text | True | — | Accès par abonnement associé à la sélection, s'il existe. |
| `reasons` | jsonb | False | '{}'::jsonb | Justifications structurées de la sélection ; JSON extensible. |

constraints :

```sql
FOREIGN KEY (model_id) REFERENCES models.canonical(model_id)
PRIMARY KEY (run_id, task, level, rank)
FOREIGN KEY (run_id) REFERENCES models.runs(run_id) ON DELETE CASCADE
FOREIGN KEY (task) REFERENCES models.tasks(task)
```

indexes :

```sql
CREATE UNIQUE INDEX selection_pkey ON models.selection USING btree (run_id, task, level, rank)
```

## models.shortlist (vue)

Models currently selected for some task / level: the price-change watch list

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `model_id` | text | True | — | Identifiant canonique du modèle dans le catalogue du routeur. |
| `name` | text | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `tasks` | text[] | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `why` | text[] | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |

Définition de la vue :

```sql
WITH s AS (
         SELECT selection.model_id,
            selection.task,
            (('top '::text || selection.level) || ' #'::text) || selection.rank AS why
           FROM models.selection
          WHERE selection.run_id = (( SELECT latest_run.run_id
                   FROM models.latest_run)) AND (selection.task = 'general'::text AND (selection.level = ANY (ARRAY['L1'::text, 'L2'::text, 'L3'::text])) OR selection.task <> 'general'::text AND selection.level = 'best'::text AND selection.rank = 1)
        UNION ALL
         SELECT preferences.pinned_model_id,
            preferences.task,
            'favori '::text || preferences.role
           FROM models.preferences
          WHERE preferences.pinned_model_id IS NOT NULL
        UNION ALL
         SELECT k.model_id,
            k.interface,
            'sans restriction'::text
           FROM models.catalog k
             LEFT JOIN models.profiles p USING (model_id)
          WHERE COALESCE(p.content_policy, k.content_policy) <> 'standard'::text
        )
 SELECT s.model_id,
    COALESCE(c.display_name, s.model_id) AS name,
    array_agg(DISTINCT s.task ORDER BY s.task) AS tasks,
    array_agg(DISTINCT s.why ORDER BY s.why) AS why
   FROM s
     JOIN models.canonical c USING (model_id)
  GROUP BY s.model_id, c.display_name;
```

## models.snapshots (table)

One fetch of a source (kind = aa, mm, da, arena, bridgebench, aa_decision, aa_stt, agentset, mteb, openrouter, kie, codex, hermes_providers, declared); raw document kept, deduplicated by sha256, 30-day retention, latest per kind always kept

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `snapshot_id` | bigint | False | nextval('models.snapshots_snapshot_id_seq'::regclass) | Référence au relevé de source dont provient cette ligne. |
| `kind` | text | False | — | Catégorie du fait, de l'alerte ou de l'exécution. |
| `fetched_at` | timestamp with time zone | False | — | Date de collecte de la source. |
| `source_url` | text | True | — | URL de provenance, sans secret. |
| `sha256` | text | False | — | Empreinte de contenu utilisée pour la déduplication. |
| `row_count` | integer | False | — | Nombre d'éléments lus dans la source. |
| `raw` | jsonb | False | — | Source brute collectée ; structure externe extensible, non instruction et non configuration. |

constraints :

```sql
UNIQUE (kind, sha256)
PRIMARY KEY (snapshot_id)
```

indexes :

```sql
CREATE INDEX snapshots_kind_at ON models.snapshots USING btree (kind, fetched_at DESC)
CREATE UNIQUE INDEX snapshots_kind_sha256_key ON models.snapshots USING btree (kind, sha256)
CREATE UNIQUE INDEX snapshots_pkey ON models.snapshots USING btree (snapshot_id)
```

## models.subscription_costs (table)

Cost price of a token through each subscription: plan price / API value carried per month (at the current pace and at full capacity). Recorded by research plans

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `sub_id` | text | False | — | Identifiant du forfait dans les déclarations de l'instance. |
| `at` | timestamp with time zone | False | now() | Horodatage du fait enregistré. |
| `price_usd_month` | double precision | False | — | Montant mensuel du forfait, en USD. |
| `api_value_month_pace` | double precision | True | — | Valeur API équivalente extrapolée au rythme d'usage observé sur un mois. |
| `api_value_month_full` | double precision | True | — | Valeur API équivalente estimée à capacité complète sur un mois. |
| `ratio_pace` | double precision | True | — | Prix mensuel divisé par valeur API équivalente au rythme observé ; ratio, pas pourcentage. |
| `ratio_full` | double precision | True | — | Prix mensuel divisé par valeur API équivalente à pleine capacité ; ratio. |
| `used_percent` | double precision | True | — | Quota consommé, en pourcentage 0..100, observé ou estimé selon la source. |
| `detail` | jsonb | False | '{}'::jsonb | Détails structurés de la mesure ou du contrôle ; JSON extensible. |

constraints :

```sql
PRIMARY KEY (sub_id, at)
```

indexes :

```sql
CREATE UNIQUE INDEX subscription_costs_pkey ON models.subscription_costs USING btree (sub_id, at)
```

## models.subscription_usage (table)

Subscription quota readings (ChatGPT Plus real via Codex, Claude Pro estimated from Claude Code transcripts); information only

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `reading_id` | bigint | False | nextval('models.subscription_usage_reading_id_seq'::regclass) | Identifiant d'un relevé de quota. |
| `sub_id` | text | False | — | Identifiant du forfait dans les déclarations de l'instance. |
| `read_at` | timestamp with time zone | False | now() | Date du relevé. |
| `window_name` | text | False | — | Fenêtre du quota (weekly, fenêtre courte, etc.). |
| `used_percent` | numeric(6,2) | False | — | Quota consommé, en pourcentage 0..100, observé ou estimé selon la source. |
| `resets_at` | timestamp with time zone | True | — | Date annoncée de réinitialisation du quota. |
| `source` | text | False | — | Provenance ou méthode de mesure ; ce champ n'est pas une preuve d'exécution à lui seul. |
| `estimated` | boolean | False | false | Indique une estimation ; ne pas la présenter comme une mesure directe. |
| `detail` | jsonb | False | '{}'::jsonb | Détails structurés de la mesure ou du contrôle ; JSON extensible. |

constraints :

```sql
PRIMARY KEY (reading_id)
```

indexes :

```sql
CREATE INDEX subscription_usage_latest ON models.subscription_usage USING btree (sub_id, window_name, read_at DESC)
CREATE UNIQUE INDEX subscription_usage_pkey ON models.subscription_usage USING btree (reading_id)
```

## models.task_benchmarks (table)

Boards that rank each task and their weights (scoring.composite); shown under each task on the library page. Sources: AA (intelligence, evaluations aa_eval, media aa_mm, decision, STT), Arena, Design Arena, BridgeBench, Agentset, MTEB

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `task` | text | False | — | Clé de tâche/poste du routeur, reliée au registre models.tasks. |
| `benchmark` | text | False | — | Famille du benchmark ; bench_task/task désigne son sous-classement. |
| `bench_task` | text | False | — | Sous-classement de la famille de benchmark affecté à la tâche. |
| `is_primary` | boolean | False | false | Benchmark principal, utilisé aussi pour certaines exigences d'éligibilité. |
| `weight` | real | False | 1.0 | Poids relatif utilisé par le classement ou l'affinité, selon la table. |
| `note` | text | True | — | Explication ou précision attachée à la donnée. |

constraints :

```sql
PRIMARY KEY (task, benchmark, bench_task)
FOREIGN KEY (task) REFERENCES models.tasks(task) ON DELETE CASCADE
```

indexes :

```sql
CREATE UNIQUE INDEX task_benchmarks_pkey ON models.task_benchmarks USING btree (task, benchmark, bench_task)
```

## models.tasks (table)

Router tasks: interface, default objective, intent_hint for the classifier, internal (module postes never offered to the classifier), requirements, consumers

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `task` | text | False | — | Clé de tâche/poste du routeur, reliée au registre models.tasks. |
| `label` | text | False | — | Libellé lisible de la tâche ou du rôle. |
| `interface` | text | False | — | Famille d'interface : chat, image, video, audio, music, transcription, embedding, rerank… |
| `quality_benchmark` | text | True | — | Famille de benchmark de qualité historique de la tâche. |
| `quality_task` | text | True | — | Sous-classement de qualité historique de la tâche. |
| `default_objective` | text | False | — | Objectif de sélection par défaut pour cette tâche. |
| `description` | text | True | — | Description fonctionnelle. |
| `modes` | text[] | False | '{}'::text[] | Modalités acceptées ou modes de génération (image, video, t2i, i2v…), selon la table. |
| `intent_hint` | text | True | — | Indication destinée au classificateur d'intention. |
| `requirements` | jsonb | False | '{}'::jsonb | Exigences de tâche : contexte minimal, benchmark principal, latence, raisonnement, impact d'un changement ; JSON extensible. |
| `internal` | boolean | False | false | Poste interne aux modules, à exclure des spécialités proposées à l'orchestrateur. |
| `consumers` | text | True | — | Modules consommateurs déclarés de ce poste. |

constraints :

```sql
CHECK ((default_objective = ANY (ARRAY['value'::text, 'best_available'::text, 'tool'::text, 'level'::text])))
PRIMARY KEY (task)
```

indexes :

```sql
CREATE UNIQUE INDEX tasks_pkey ON models.tasks USING btree (task)
```

## models.usable_endpoints (vue)

Hosts of the latest snapshot that are reliable (>= 95 % over 24 h) and not below the vendor's own precision

| Colonne | Type SQL | Nullable | Défaut SQL | Signification |
|---|---|---|---|---|
| `snapshot_id` | bigint | True | — | Référence au relevé de source dont provient cette ligne. |
| `gateway` | text | True | — | Passerelle derrière laquelle cet hébergeur est accessible. |
| `model_id` | text | True | — | Identifiant canonique du modèle dans le catalogue du routeur. |
| `gateway_model` | text | True | — | Identifiant du modèle utilisé par cette passerelle. |
| `host` | text | True | — | Hébergeur effectif derrière une passerelle. |
| `tag` | text | True | — | Identifiant de routage de l'hébergeur. |
| `quantization` | text | True | — | Précision numérique annoncée : bf16, fp8, mxfp4, etc. |
| `price_in_1m` | double precision | True | — | Prix USD par million de tokens d'entrée. |
| `price_out_1m` | double precision | True | — | Prix USD par million de tokens de sortie. |
| `cache_read_1m` | double precision | True | — | Prix USD par million de tokens lus dans le cache, si publié. |
| `context_length` | bigint | True | — | Capacité de contexte annoncée, en tokens ; distincte d'un budget effectif de qualité. |
| `uptime_1d` | double precision | True | — | Taux de réussite/disponibilité sur 24 heures tel que fourni par la source. |
| `uptime_30m` | double precision | True | — | Taux de réussite/disponibilité sur 30 minutes tel que fourni par la source. |
| `status` | integer | True | — | État de l'objet (alerte, cycle ou disponibilité selon la table). |
| `latency_ms` | double precision | True | — | Latence mesurée ou annoncée, en millisecondes. |
| `throughput_tps` | double precision | True | — | Débit annoncé en tokens par seconde. |
| `tools` | boolean | True | — | Prise en charge annoncée des appels d'outils. |
| `structured` | boolean | True | — | Prise en charge annoncée des sorties structurées. |
| `service_tier` | text | True | — | Classe de service de l'hébergeur (flex, standard, priority…). |
| `blended_1m` | double precision | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |
| `vendor_quantization` | text | True | — | Champ dérivé ; expression complète dans la définition SQL de cette vue. |

Définition de la vue :

```sql
WITH latest AS (
         SELECT endpoints.snapshot_id,
            endpoints.gateway,
            endpoints.model_id,
            endpoints.gateway_model,
            endpoints.host,
            endpoints.tag,
            endpoints.quantization,
            endpoints.price_in_1m,
            endpoints.price_out_1m,
            endpoints.cache_read_1m,
            endpoints.context_length,
            endpoints.uptime_1d,
            endpoints.uptime_30m,
            endpoints.status,
            endpoints.latency_ms,
            endpoints.throughput_tps,
            endpoints.tools,
            endpoints.structured,
            endpoints.service_tier
           FROM models.endpoints
          WHERE endpoints.snapshot_id = (( SELECT latest_snapshots.snapshot_id
                   FROM models.latest_snapshots
                  WHERE latest_snapshots.kind = 'or_endpoints'::text))
        ), vendor AS (
         SELECT DISTINCT ON (latest.gateway_model) latest.gateway_model,
            latest.quantization AS native
           FROM latest
          WHERE split_part(latest.tag, '/'::text, 1) = split_part(latest.gateway_model, '/'::text, 1)
          ORDER BY latest.gateway_model, latest.price_in_1m
        )
 SELECT l.snapshot_id,
    l.gateway,
    l.model_id,
    l.gateway_model,
    l.host,
    l.tag,
    l.quantization,
    l.price_in_1m,
    l.price_out_1m,
    l.cache_read_1m,
    l.context_length,
    l.uptime_1d,
    l.uptime_30m,
    l.status,
    l.latency_ms,
    l.throughput_tps,
    l.tools,
    l.structured,
    l.service_tier,
    (3::double precision * l.price_in_1m + l.price_out_1m) / 4::double precision AS blended_1m,
    v.native AS vendor_quantization
   FROM latest l
     LEFT JOIN vendor v USING (gateway_model)
  WHERE l.price_in_1m IS NOT NULL AND COALESCE(l.uptime_1d, 100::double precision) >= 95::double precision AND (COALESCE(l.quantization, 'unknown'::text) !~ '(fp4|int4|fp6|int6)'::text OR l.quantization = v.native);
```

