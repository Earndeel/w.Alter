-- Walter Memory — base structure of the kardex schema (social layer of Walter Memory, A10).
-- 2026-10-29 (Walter Clean): kardex was created by the retired kardex service's own migrations (2026-09/10) and grown
-- by hand; no migration of this module created it, so a blank database could not be built. This file is that
-- structure as it stands in the first instance's live database, exported with pg_dump --schema-only (no row, no
-- owner, no privilege) and reviewed. It runs only when the kardex schema does not exist yet: on an existing database
-- it changes nothing. Later changes go in later migrations, never here.
do $walter_kardex_base$
begin
  if to_regnamespace('kardex') is null then
    execute $ddl$
CREATE SCHEMA kardex;

CREATE TABLE kardex.action_recommendations (
    id bigint NOT NULL,
    contact_id integer,
    open_loop_id bigint,
    action_type text NOT NULL,
    description text NOT NULL,
    priority text DEFAULT 'normal'::text,
    risk_level text DEFAULT 'low'::text,
    deadline_at timestamp with time zone,
    reason text,
    suggested_message text,
    suggested_style text,
    avoid_saying text[] DEFAULT '{}'::text[],
    status text DEFAULT 'pending'::text,
    confidence double precision DEFAULT 0.5,
    extraction_run_id bigint,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.action_recommendations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.action_recommendations_id_seq OWNED BY kardex.action_recommendations.id;

CREATE TABLE kardex.actions (
    id integer NOT NULL,
    contact_id integer,
    action_type text NOT NULL,
    description text NOT NULL,
    priority text DEFAULT 'normal'::text,
    due_date date,
    source text,
    source_message_id integer,
    status text DEFAULT 'pending'::text,
    created_at timestamp with time zone DEFAULT now(),
    completed_at timestamp with time zone
);

CREATE SEQUENCE kardex.actions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.actions_id_seq OWNED BY kardex.actions.id;

CREATE TABLE kardex.boundaries (
    id bigint NOT NULL,
    contact_id integer,
    boundary_type text NOT NULL,
    boundary text NOT NULL,
    explicitness text DEFAULT 'inferred'::text,
    severity text DEFAULT 'medium'::text,
    status text DEFAULT 'active'::text,
    confidence double precision DEFAULT 0.5,
    claim_id bigint,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.boundaries_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.boundaries_id_seq OWNED BY kardex.boundaries.id;

CREATE TABLE kardex.channels (
    id integer NOT NULL,
    contact_id integer,
    platform text NOT NULL,
    platform_id text,
    platform_handle text,
    is_primary boolean DEFAULT false,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.channels_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.channels_id_seq OWNED BY kardex.channels.id;

CREATE TABLE kardex.claim_evidence (
    claim_id bigint NOT NULL,
    evidence_id bigint NOT NULL,
    role text DEFAULT 'supporting'::text NOT NULL,
    weight double precision DEFAULT 1.0,
    created_at timestamp with time zone DEFAULT now()
);

CREATE TABLE kardex.claims (
    id bigint NOT NULL,
    contact_id integer,
    claim_type text NOT NULL,
    category text,
    claim text NOT NULL,
    claim_json jsonb DEFAULT '{}'::jsonb,
    status text DEFAULT 'active'::text,
    confidence double precision DEFAULT 0.5,
    stability text DEFAULT 'unknown'::text,
    valid_from timestamp with time zone,
    valid_to timestamp with time zone,
    extraction_method text DEFAULT 'unknown'::text,
    extraction_run_id bigint,
    supersedes_claim_id bigint,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    knowledge_origin text DEFAULT 'unknown'::text NOT NULL,
    disclosure_state text DEFAULT 'externally_discovered'::text NOT NULL,
    mention_policy text DEFAULT 'contextual_only'::text NOT NULL,
    sensitivity text DEFAULT 'normal'::text NOT NULL,
    owner_knows boolean,
    contact_told_owner boolean,
    contact_knows_owner_knows boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_claims_disclosure_state CHECK ((disclosure_state = ANY (ARRAY['explicitly_told_me'::text, 'mutually_known'::text, 'plausibly_known'::text, 'externally_discovered'::text, 'inferred_only'::text, 'restricted'::text, 'unknown'::text]))),
    CONSTRAINT ck_claims_knowledge_origin CHECK ((knowledge_origin = ANY (ARRAY['direct_statement'::text, 'observed_behavior'::text, 'shared_contact'::text, 'public_osint'::text, 'private_osint'::text, 'inference'::text, 'user_supplied'::text, 'system_observation'::text, 'unknown'::text]))),
    CONSTRAINT ck_claims_mention_policy CHECK ((mention_policy = ANY (ARRAY['free'::text, 'contextual_only'::text, 'indirect_only'::text, 'never_reference'::text]))),
    CONSTRAINT ck_claims_sensitivity CHECK ((sensitivity = ANY (ARRAY['normal'::text, 'personal'::text, 'sensitive'::text, 'highly_sensitive'::text])))
);

COMMENT ON TABLE kardex.claims IS 'Atomic evidence-backed claims. Synthetic layers should derive from these, not from vibes.';

CREATE SEQUENCE kardex.claims_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.claims_id_seq OWNED BY kardex.claims.id;

CREATE TABLE kardex.communication_deviations (
    deviation_id bigint NOT NULL,
    entity_id uuid NOT NULL,
    metric text NOT NULL,
    baseline real,
    current real,
    ratio real,
    baseline_window text NOT NULL,
    current_window text NOT NULL,
    sample_size integer NOT NULL,
    observation text NOT NULL,
    confidence text DEFAULT 'low'::text NOT NULL,
    detected_on date DEFAULT CURRENT_DATE NOT NULL,
    acknowledged_at timestamp with time zone,
    processor_version text NOT NULL
);

CREATE SEQUENCE kardex.communication_deviations_deviation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.communication_deviations_deviation_id_seq OWNED BY kardex.communication_deviations.deviation_id;

CREATE TABLE kardex.communication_patterns (
    id bigint NOT NULL,
    contact_id integer,
    pattern_type text NOT NULL,
    pattern text NOT NULL,
    metric_value jsonb DEFAULT '{}'::jsonb,
    confidence double precision DEFAULT 0.5,
    status text DEFAULT 'active'::text,
    claim_id bigint,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.communication_patterns_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.communication_patterns_id_seq OWNED BY kardex.communication_patterns.id;

CREATE TABLE kardex.contact_merge_audit (
    id bigint NOT NULL,
    action text NOT NULL,
    source_contact_id integer,
    target_contact_id integer,
    actor text DEFAULT 'system'::text,
    reason text,
    evidence jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.contact_merge_audit_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.contact_merge_audit_id_seq OWNED BY kardex.contact_merge_audit.id;

CREATE TABLE kardex.contact_merge_candidates (
    id bigint NOT NULL,
    source_contact_id integer,
    target_contact_id integer,
    reason text NOT NULL,
    evidence jsonb DEFAULT '{}'::jsonb,
    confidence double precision DEFAULT 0.0,
    status text DEFAULT 'pending'::text,
    created_at timestamp with time zone DEFAULT now(),
    reviewed_at timestamp with time zone
);

CREATE SEQUENCE kardex.contact_merge_candidates_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.contact_merge_candidates_id_seq OWNED BY kardex.contact_merge_candidates.id;

CREATE TABLE kardex.contacts (
    id integer NOT NULL,
    canonical_name text NOT NULL,
    aliases text[] DEFAULT '{}'::text[],
    phone_numbers text[] DEFAULT '{}'::text[],
    emails text[] DEFAULT '{}'::text[],
    handles jsonb DEFAULT '{}'::jsonb,
    nationality text,
    languages text[] DEFAULT '{}'::text[],
    location_current text,
    location_home text,
    age_approx text,
    occupation text,
    photo_url text,
    relationship_type text,
    relationship_status text,
    first_contact_date timestamp with time zone,
    last_contact_date timestamp with time zone,
    contact_frequency text,
    personality_profile text,
    communication_style text,
    interests text[] DEFAULT '{}'::text[],
    preferences jsonb DEFAULT '{}'::jsonb,
    key_facts text[] DEFAULT '{}'::text[],
    total_messages integer DEFAULT 0,
    total_media integer DEFAULT 0,
    sources text[] DEFAULT '{}'::text[],
    context_last_updated timestamp with time zone,
    raw_context text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    contact_uuid uuid DEFAULT gen_random_uuid(),
    identity_status text DEFAULT 'active'::text,
    merge_confidence double precision DEFAULT 1.0,
    last_context_pack jsonb DEFAULT '{}'::jsonb,
    entity_id bigint
);

CREATE TABLE kardex.events (
    id integer NOT NULL,
    contact_id integer,
    event_type text NOT NULL,
    title text NOT NULL,
    description text,
    event_date date,
    event_time time without time zone,
    is_recurring boolean DEFAULT false,
    recurrence text,
    source text,
    source_message_id integer,
    confidence double precision DEFAULT 0.5,
    status text DEFAULT 'upcoming'::text,
    reminded boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

CREATE TABLE kardex.media (
    id integer NOT NULL,
    contact_id integer,
    message_id integer,
    media_type text NOT NULL,
    file_format text,
    file_size bigint,
    source_path text,
    local_path text,
    is_analyzed boolean DEFAULT false,
    analysis_text text,
    analysis_model text,
    analysis_timestamp timestamp with time zone,
    "timestamp" timestamp with time zone,
    raw jsonb,
    created_at timestamp with time zone DEFAULT now()
);

CREATE TABLE kardex.messages (
    id integer NOT NULL,
    contact_id integer,
    channel_id integer,
    source text NOT NULL,
    sender text NOT NULL,
    text text,
    "timestamp" timestamp with time zone NOT NULL,
    has_attachments boolean DEFAULT false,
    attachment_types text[] DEFAULT '{}'::text[],
    source_message_id text,
    raw jsonb,
    created_at timestamp with time zone DEFAULT now()
);

CREATE VIEW kardex.contact_summary AS
 SELECT id,
    canonical_name,
    relationship_type,
    relationship_status,
    location_current,
    personality_profile,
    interests,
    total_messages,
    total_media,
    last_contact_date,
    sources,
    ( SELECT count(*) AS count
           FROM kardex.messages m
          WHERE (m.contact_id = c.id)) AS actual_messages,
    ( SELECT count(*) AS count
           FROM kardex.media me
          WHERE ((me.contact_id = c.id) AND (me.is_analyzed = true))) AS analyzed_media,
    ( SELECT count(*) AS count
           FROM kardex.events e
          WHERE ((e.contact_id = c.id) AND (e.status = 'upcoming'::text))) AS upcoming_events,
    ( SELECT count(*) AS count
           FROM kardex.actions a
          WHERE ((a.contact_id = c.id) AND (a.status = 'pending'::text))) AS pending_actions
   FROM kardex.contacts c;

CREATE SEQUENCE kardex.contacts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.contacts_id_seq OWNED BY kardex.contacts.id;

CREATE TABLE kardex.context_packs (
    id bigint NOT NULL,
    contact_id integer,
    pack_type text NOT NULL,
    purpose text NOT NULL,
    content text NOT NULL,
    token_estimate integer,
    source_claim_ids bigint[] DEFAULT '{}'::bigint[],
    source_episode_ids bigint[] DEFAULT '{}'::bigint[],
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.context_packs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.context_packs_id_seq OWNED BY kardex.context_packs.id;

CREATE TABLE kardex.conversation_episodes (
    id bigint NOT NULL,
    contact_id integer,
    source_thread_ids bigint[] DEFAULT '{}'::bigint[],
    start_at timestamp with time zone NOT NULL,
    end_at timestamp with time zone NOT NULL,
    title text,
    summary_factual text,
    summary_emotional text,
    topics text[] DEFAULT '{}'::text[],
    emotional_tone text[] DEFAULT '{}'::text[],
    relationship_impact text,
    importance integer DEFAULT 1,
    message_count integer DEFAULT 0,
    media_count integer DEFAULT 0,
    open_loop_count integer DEFAULT 0,
    extraction_run_id bigint,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT conversation_episodes_importance_check CHECK (((importance >= 1) AND (importance <= 5)))
);

COMMENT ON TABLE kardex.conversation_episodes IS 'Conversation chunks segmented by time/topic/tone for scalable multi-year analysis.';

CREATE SEQUENCE kardex.conversation_episodes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.conversation_episodes_id_seq OWNED BY kardex.conversation_episodes.id;

CREATE TABLE kardex.corrections (
    id bigint NOT NULL,
    contact_id integer,
    correction_type text NOT NULL,
    bad_value text,
    corrected_value text,
    rule text NOT NULL,
    scope text DEFAULT 'global'::text,
    status text DEFAULT 'active'::text,
    created_by text DEFAULT 'owner'::text,
    created_at timestamp with time zone DEFAULT now()
);

COMMENT ON TABLE kardex.corrections IS 'Owner corrections that become extraction rules. Example: a nickname is not an alias.';

CREATE SEQUENCE kardex.corrections_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.corrections_id_seq OWNED BY kardex.corrections.id;

CREATE TABLE kardex.disclosure_transitions (
    id bigint NOT NULL,
    claim_id bigint NOT NULL,
    from_state text,
    to_state text NOT NULL,
    from_policy text,
    to_policy text NOT NULL,
    trigger_evidence_id bigint,
    trigger_reason text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE SEQUENCE kardex.disclosure_transitions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.disclosure_transitions_id_seq OWNED BY kardex.disclosure_transitions.id;

CREATE TABLE kardex.entities (
    id bigint NOT NULL,
    entity_type text NOT NULL,
    canonical_name text NOT NULL,
    normalized_name text NOT NULL,
    aliases text[] DEFAULT '{}'::text[] NOT NULL,
    identifiers jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    merged_into bigint,
    confidence real DEFAULT 1.0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_entities_status CHECK ((status = ANY (ARRAY['active'::text, 'merged'::text, 'inactive'::text]))),
    CONSTRAINT ck_entities_type CHECK ((entity_type = ANY (ARRAY['person'::text, 'company'::text, 'organization'::text, 'place'::text, 'school'::text, 'university'::text, 'event'::text, 'group'::text, 'project'::text, 'brand'::text])))
);

CREATE SEQUENCE kardex.entities_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.entities_id_seq OWNED BY kardex.entities.id;

CREATE TABLE kardex.episode_items (
    episode_id bigint NOT NULL,
    raw_item_id bigint NOT NULL,
    role text DEFAULT 'member'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.events_id_seq OWNED BY kardex.events.id;

CREATE TABLE kardex.evidence (
    id bigint NOT NULL,
    contact_id integer,
    raw_item_id bigint,
    message_id integer,
    media_id integer,
    source text NOT NULL,
    source_ref text,
    "timestamp" timestamp with time zone,
    speaker text,
    quote text,
    evidence_type text DEFAULT 'message_quote'::text,
    extraction_run_id bigint,
    confidence double precision DEFAULT 1.0,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    knowledge_origin text DEFAULT 'unknown'::text NOT NULL,
    source_url text,
    acquired_at timestamp with time zone DEFAULT now() NOT NULL,
    sensitivity text DEFAULT 'normal'::text NOT NULL,
    CONSTRAINT ck_evidence_knowledge_origin CHECK ((knowledge_origin = ANY (ARRAY['direct_statement'::text, 'observed_behavior'::text, 'shared_contact'::text, 'public_osint'::text, 'private_osint'::text, 'inference'::text, 'user_supplied'::text, 'system_observation'::text, 'unknown'::text])))
);

COMMENT ON TABLE kardex.evidence IS 'Evidence snippets used to support or counter extracted claims.';

CREATE SEQUENCE kardex.evidence_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.evidence_id_seq OWNED BY kardex.evidence.id;

CREATE TABLE kardex.extraction_runs (
    id bigint NOT NULL,
    run_uuid uuid DEFAULT gen_random_uuid(),
    contact_id integer,
    source text NOT NULL,
    stage text NOT NULL,
    model text,
    prompt_version text,
    input_item_count integer DEFAULT 0,
    output_item_count integer DEFAULT 0,
    status text DEFAULT 'running'::text,
    error_message text,
    metadata jsonb DEFAULT '{}'::jsonb,
    started_at timestamp with time zone DEFAULT now(),
    finished_at timestamp with time zone
);

CREATE SEQUENCE kardex.extraction_runs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.extraction_runs_id_seq OWNED BY kardex.extraction_runs.id;

CREATE TABLE kardex.health_notes (
    id bigint NOT NULL,
    contact_id integer,
    note_type text NOT NULL,
    note text NOT NULL,
    sensitivity text DEFAULT 'normal'::text,
    status text DEFAULT 'active'::text,
    occurred_at timestamp with time zone,
    confidence double precision DEFAULT 0.5,
    claim_id bigint,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.health_notes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.health_notes_id_seq OWNED BY kardex.health_notes.id;

CREATE TABLE kardex.hindsight_sync_state (
    table_name text NOT NULL,
    last_synced_id bigint DEFAULT 0,
    updated_at timestamp with time zone DEFAULT now()
);

CREATE TABLE kardex.identity_clusters (
    id bigint NOT NULL,
    canonical_contact_id integer,
    status text DEFAULT 'unresolved'::text,
    cluster_label text,
    confidence double precision DEFAULT 0.0,
    evidence_summary text,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.identity_clusters_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.identity_clusters_id_seq OWNED BY kardex.identity_clusters.id;

CREATE TABLE kardex.identity_links (
    id bigint NOT NULL,
    identity_cluster_id bigint,
    contact_id integer,
    source text NOT NULL,
    identifier_type text NOT NULL,
    identifier_value text NOT NULL,
    normalized_value text,
    strength text DEFAULT 'weak'::text,
    confidence double precision DEFAULT 0.0,
    status text DEFAULT 'active'::text,
    evidence_id bigint,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.identity_links_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.identity_links_id_seq OWNED BY kardex.identity_links.id;

CREATE TABLE kardex.identity_mentions (
    id bigint NOT NULL,
    contact_id integer,
    raw_item_id bigint,
    message_id integer,
    mention_text text NOT NULL,
    mention_type text NOT NULL,
    used_by text,
    used_for text,
    context_window text,
    confidence double precision DEFAULT 0.5,
    is_valid_alias boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.identity_mentions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.identity_mentions_id_seq OWNED BY kardex.identity_mentions.id;

CREATE TABLE kardex.journal_entries (
    id bigint NOT NULL,
    contact_id integer DEFAULT 0 NOT NULL,
    content text NOT NULL,
    title text,
    mood text,
    energy_level smallint,
    emotional_tags text[] DEFAULT '{}'::text[],
    context text,
    related_contacts integer[],
    related_topics text[] DEFAULT '{}'::text[],
    entry_type text DEFAULT 'thought'::text,
    privacy_level text DEFAULT 'intimate'::text,
    entry_date date DEFAULT CURRENT_DATE,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    source text DEFAULT 'direct'::text,
    source_ref text,
    CONSTRAINT journal_entries_energy_level_check CHECK (((energy_level >= 1) AND (energy_level <= 10)))
);

COMMENT ON TABLE kardex.journal_entries IS 'Journal intime — pensées brutes, rêves, réflexions profondes. Jamais exposé tel quel, sert de matière première pour le profil psychologique.';

CREATE SEQUENCE kardex.journal_entries_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.journal_entries_id_seq OWNED BY kardex.journal_entries.id;

CREATE SEQUENCE kardex.media_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.media_id_seq OWNED BY kardex.media.id;

CREATE SEQUENCE kardex.messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.messages_id_seq OWNED BY kardex.messages.id;

CREATE TABLE kardex.open_loops (
    id bigint NOT NULL,
    contact_id integer,
    episode_id bigint,
    loop_type text NOT NULL,
    description text NOT NULL,
    opened_at timestamp with time zone,
    deadline_at timestamp with time zone,
    priority text DEFAULT 'normal'::text,
    status text DEFAULT 'open'::text,
    closure_reason text,
    confidence double precision DEFAULT 0.5,
    claim_id bigint,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.open_loops_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.open_loops_id_seq OWNED BY kardex.open_loops.id;

CREATE VIEW kardex.pending_actions AS
 SELECT a.id,
    a.contact_id,
    a.action_type,
    a.description,
    a.priority,
    a.due_date,
    a.source,
    a.source_message_id,
    a.status,
    a.created_at,
    a.completed_at,
    c.canonical_name AS contact_name
   FROM (kardex.actions a
     JOIN kardex.contacts c ON ((c.id = a.contact_id)))
  WHERE (a.status = 'pending'::text)
  ORDER BY
        CASE a.priority
            WHEN 'urgent'::text THEN 1
            WHEN 'high'::text THEN 2
            WHEN 'normal'::text THEN 3
            WHEN 'low'::text THEN 4
            ELSE NULL::integer
        END, a.due_date;

CREATE TABLE kardex.preferences (
    id bigint NOT NULL,
    contact_id integer,
    category text NOT NULL,
    preference text NOT NULL,
    polarity text DEFAULT 'likes'::text,
    strength double precision DEFAULT 0.5,
    status text DEFAULT 'active'::text,
    confidence double precision DEFAULT 0.5,
    claim_id bigint,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.preferences_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.preferences_id_seq OWNED BY kardex.preferences.id;

CREATE TABLE kardex.psychological_claims (
    id bigint NOT NULL,
    contact_id integer,
    dimension text NOT NULL,
    claim text NOT NULL,
    confidence double precision DEFAULT 0.5,
    stability text DEFAULT 'unknown'::text,
    trigger_patterns text[] DEFAULT '{}'::text[],
    counter_patterns text[] DEFAULT '{}'::text[],
    strategy_implication text,
    claim_id bigint,
    extraction_run_id bigint,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.psychological_claims_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.psychological_claims_id_seq OWNED BY kardex.psychological_claims.id;

CREATE TABLE kardex.raw_items (
    id bigint NOT NULL,
    contact_id integer,
    source_thread_id bigint,
    message_id integer,
    media_id integer,
    source text NOT NULL,
    source_account text,
    external_id text NOT NULL,
    item_type text NOT NULL,
    direction text,
    speaker text,
    "timestamp" timestamp with time zone,
    text_content text,
    attachment_refs jsonb DEFAULT '[]'::jsonb,
    raw_payload jsonb DEFAULT '{}'::jsonb,
    content_hash text,
    created_at timestamp with time zone DEFAULT now()
);

COMMENT ON TABLE kardex.raw_items IS 'Immutable normalized source items from Beeper, Gmail, Android, WhatsApp, calls, calendar, etc.';

CREATE SEQUENCE kardex.raw_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.raw_items_id_seq OWNED BY kardex.raw_items.id;

CREATE TABLE kardex.recommendations (
    id bigint NOT NULL,
    contact_id integer,
    item_type text NOT NULL,
    item_name text NOT NULL,
    recommended_by text,
    status text DEFAULT 'mentioned'::text,
    notes text,
    claim_id bigint,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.recommendations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.recommendations_id_seq OWNED BY kardex.recommendations.id;

CREATE TABLE kardex.rel_disclosure_transitions (
    id bigint NOT NULL,
    relationship_id bigint NOT NULL,
    from_state text,
    to_state text NOT NULL,
    to_policy text NOT NULL,
    trigger_evidence_id bigint,
    trigger_reason text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE SEQUENCE kardex.rel_disclosure_transitions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.rel_disclosure_transitions_id_seq OWNED BY kardex.rel_disclosure_transitions.id;

CREATE TABLE kardex.relationship_baselines (
    entity_id uuid NOT NULL,
    window_name text NOT NULL,
    channels text[] DEFAULT '{}'::text[] NOT NULL,
    messages integer NOT NULL,
    from_me integer NOT NULL,
    from_them integer NOT NULL,
    msgs_per_day real,
    active_days integer,
    initiation_ratio_me real,
    median_reply_me_s real,
    median_reply_them_s real,
    avg_len_me real,
    avg_len_them real,
    first_contact timestamp with time zone,
    last_contact timestamp with time zone,
    computed_at timestamp with time zone DEFAULT now() NOT NULL,
    processor_version text NOT NULL,
    CONSTRAINT relationship_baselines_window_name_check CHECK ((window_name = ANY (ARRAY['7d'::text, '14d'::text, '30d'::text, '90d'::text, '365d'::text, 'all'::text])))
);

CREATE TABLE kardex.relationship_events (
    id bigint NOT NULL,
    contact_id integer,
    episode_id bigint,
    event_type text NOT NULL,
    title text NOT NULL,
    description text,
    date_start timestamp with time zone,
    date_end timestamp with time zone,
    participants text[] DEFAULT '{}'::text[],
    emotional_tone text[] DEFAULT '{}'::text[],
    relationship_impact text,
    importance integer DEFAULT 1,
    status text DEFAULT 'confirmed'::text,
    confidence double precision DEFAULT 0.5,
    extraction_run_id bigint,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT relationship_events_importance_check CHECK (((importance >= 1) AND (importance <= 5)))
);

CREATE SEQUENCE kardex.relationship_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.relationship_events_id_seq OWNED BY kardex.relationship_events.id;

CREATE TABLE kardex.relationship_evidence (
    relationship_id bigint NOT NULL,
    evidence_id bigint NOT NULL,
    role text DEFAULT 'supports'::text NOT NULL,
    weight real DEFAULT 1.0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT relationship_evidence_role_check CHECK ((role = ANY (ARRAY['supports'::text, 'contradicts'::text])))
);

CREATE TABLE kardex.relationship_metrics (
    id bigint NOT NULL,
    contact_id integer,
    metric_name text NOT NULL,
    metric_period text,
    period_start timestamp with time zone,
    period_end timestamp with time zone,
    metric_value jsonb NOT NULL,
    computed_from_count integer DEFAULT 0,
    extraction_run_id bigint,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.relationship_metrics_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.relationship_metrics_id_seq OWNED BY kardex.relationship_metrics.id;

CREATE TABLE kardex.relationships (
    id bigint NOT NULL,
    source_entity_id bigint NOT NULL,
    target_entity_id bigint NOT NULL,
    relationship_type text NOT NULL,
    directionality text DEFAULT 'directed'::text NOT NULL,
    status text DEFAULT 'proposed'::text NOT NULL,
    confidence real DEFAULT 0.7 NOT NULL,
    valid_from timestamp with time zone,
    valid_to timestamp with time zone,
    knowledge_origin text DEFAULT 'unknown'::text NOT NULL,
    disclosure_state text DEFAULT 'externally_discovered'::text NOT NULL,
    mention_policy text DEFAULT 'contextual_only'::text NOT NULL,
    sensitivity text DEFAULT 'normal'::text NOT NULL,
    supersedes_rel_id bigint,
    claim_id bigint,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT relationships_check CHECK ((source_entity_id <> target_entity_id)),
    CONSTRAINT relationships_directionality_check CHECK ((directionality = ANY (ARRAY['directed'::text, 'symmetric'::text]))),
    CONSTRAINT relationships_disclosure_state_check CHECK ((disclosure_state = ANY (ARRAY['explicitly_told_me'::text, 'mutually_known'::text, 'plausibly_known'::text, 'externally_discovered'::text, 'inferred_only'::text, 'restricted'::text, 'unknown'::text]))),
    CONSTRAINT relationships_knowledge_origin_check CHECK ((knowledge_origin = ANY (ARRAY['direct_statement'::text, 'observed_behavior'::text, 'shared_contact'::text, 'public_osint'::text, 'private_osint'::text, 'inference'::text, 'user_supplied'::text, 'system_observation'::text, 'unknown'::text]))),
    CONSTRAINT relationships_mention_policy_check CHECK ((mention_policy = ANY (ARRAY['free'::text, 'contextual_only'::text, 'indirect_only'::text, 'never_reference'::text]))),
    CONSTRAINT relationships_sensitivity_check CHECK ((sensitivity = ANY (ARRAY['normal'::text, 'personal'::text, 'sensitive'::text, 'highly_sensitive'::text]))),
    CONSTRAINT relationships_status_check CHECK ((status = ANY (ARRAY['proposed'::text, 'confirmed'::text, 'ended'::text, 'superseded'::text, 'rejected'::text])))
);

CREATE SEQUENCE kardex.relationships_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.relationships_id_seq OWNED BY kardex.relationships.id;

CREATE TABLE kardex.social_graph (
    id bigint NOT NULL,
    contact_id integer,
    related_person_name text NOT NULL,
    relationship_to_contact text,
    relationship_to_owner text,
    importance integer DEFAULT 1,
    notes text,
    status text DEFAULT 'active'::text,
    confidence double precision DEFAULT 0.5,
    claim_id bigint,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT social_graph_importance_check CHECK (((importance >= 1) AND (importance <= 5)))
);

CREATE SEQUENCE kardex.social_graph_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.social_graph_id_seq OWNED BY kardex.social_graph.id;

CREATE TABLE kardex.source_threads (
    id bigint NOT NULL,
    contact_id integer,
    channel_id integer,
    source text NOT NULL,
    source_account text,
    external_thread_id text NOT NULL,
    platform_handle text,
    title text,
    participant_snapshot jsonb DEFAULT '[]'::jsonb,
    first_seen_at timestamp with time zone,
    last_seen_at timestamp with time zone,
    last_synced_at timestamp with time zone,
    identity_cluster_id bigint,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.source_threads_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.source_threads_id_seq OWNED BY kardex.source_threads.id;

CREATE TABLE kardex.style_profiles (
    id bigint NOT NULL,
    contact_id integer,
    owner text NOT NULL,
    language_profile jsonb DEFAULT '{}'::jsonb,
    tone_profile jsonb DEFAULT '{}'::jsonb,
    emoji_profile jsonb DEFAULT '{}'::jsonb,
    phrase_templates jsonb DEFAULT '[]'::jsonb,
    message_length_profile jsonb DEFAULT '{}'::jsonb,
    escalation_patterns jsonb DEFAULT '{}'::jsonb,
    avoid_phrases text[] DEFAULT '{}'::text[],
    confidence double precision DEFAULT 0.5,
    extraction_run_id bigint,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

CREATE SEQUENCE kardex.style_profiles_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.style_profiles_id_seq OWNED BY kardex.style_profiles.id;

CREATE TABLE kardex.sync_state (
    id integer NOT NULL,
    source text NOT NULL,
    source_id text NOT NULL,
    contact_id integer,
    last_cursor text,
    last_synced_at timestamp with time zone,
    total_synced integer DEFAULT 0,
    status text DEFAULT 'pending'::text,
    error_message text
);

CREATE SEQUENCE kardex.sync_state_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE kardex.sync_state_id_seq OWNED BY kardex.sync_state.id;

CREATE VIEW kardex.upcoming_events AS
 SELECT e.id,
    e.contact_id,
    e.event_type,
    e.title,
    e.description,
    e.event_date,
    e.event_time,
    e.is_recurring,
    e.recurrence,
    e.source,
    e.source_message_id,
    e.confidence,
    e.status,
    e.reminded,
    e.created_at,
    e.updated_at,
    c.canonical_name AS contact_name
   FROM (kardex.events e
     JOIN kardex.contacts c ON ((c.id = e.contact_id)))
  WHERE ((e.status = 'upcoming'::text) AND (e.event_date >= CURRENT_DATE))
  ORDER BY e.event_date;

CREATE VIEW kardex.v_active_open_loops AS
 SELECT ol.id,
    ol.contact_id,
    ol.episode_id,
    ol.loop_type,
    ol.description,
    ol.opened_at,
    ol.deadline_at,
    ol.priority,
    ol.status,
    ol.closure_reason,
    ol.confidence,
    ol.claim_id,
    ol.metadata,
    ol.created_at,
    ol.updated_at,
    c.canonical_name
   FROM (kardex.open_loops ol
     JOIN kardex.contacts c ON ((c.id = ol.contact_id)))
  WHERE (ol.status = 'open'::text)
  ORDER BY
        CASE ol.priority
            WHEN 'urgent'::text THEN 1
            WHEN 'high'::text THEN 2
            WHEN 'normal'::text THEN 3
            WHEN 'low'::text THEN 4
            ELSE 5
        END, ol.deadline_at, ol.created_at DESC;

CREATE VIEW kardex.v_claims_without_evidence AS
SELECT
    NULL::bigint AS id,
    NULL::integer AS contact_id,
    NULL::text AS claim_type,
    NULL::text AS category,
    NULL::text AS claim,
    NULL::jsonb AS claim_json,
    NULL::text AS status,
    NULL::double precision AS confidence,
    NULL::text AS stability,
    NULL::timestamp with time zone AS valid_from,
    NULL::timestamp with time zone AS valid_to,
    NULL::text AS extraction_method,
    NULL::bigint AS extraction_run_id,
    NULL::bigint AS supersedes_claim_id,
    NULL::jsonb AS metadata,
    NULL::timestamp with time zone AS created_at,
    NULL::timestamp with time zone AS updated_at;

CREATE VIEW kardex.v_contact_dossier_status AS
 SELECT id AS contact_id,
    canonical_name,
    identity_status,
    relationship_type,
    relationship_status,
    last_contact_date,
    ( SELECT count(*) AS count
           FROM kardex.messages m
          WHERE (m.contact_id = c.id)) AS message_count,
    ( SELECT count(*) AS count
           FROM kardex.raw_items ri
          WHERE (ri.contact_id = c.id)) AS raw_item_count,
    ( SELECT count(*) AS count
           FROM kardex.conversation_episodes ep
          WHERE (ep.contact_id = c.id)) AS episode_count,
    ( SELECT count(*) AS count
           FROM kardex.claims cl
          WHERE ((cl.contact_id = c.id) AND (cl.status = 'active'::text))) AS active_claim_count,
    ( SELECT count(*) AS count
           FROM kardex.relationship_events re
          WHERE ((re.contact_id = c.id) AND (re.status = 'confirmed'::text))) AS event_count,
    ( SELECT count(*) AS count
           FROM kardex.open_loops ol
          WHERE ((ol.contact_id = c.id) AND (ol.status = 'open'::text))) AS open_loop_count,
    ( SELECT count(*) AS count
           FROM kardex.action_recommendations ar
          WHERE ((ar.contact_id = c.id) AND (ar.status = 'pending'::text))) AS pending_recommendation_count
   FROM kardex.contacts c;

CREATE VIEW kardex.v_unresolved_identities AS
SELECT
    NULL::bigint AS id,
    NULL::integer AS canonical_contact_id,
    NULL::text AS status,
    NULL::text AS cluster_label,
    NULL::double precision AS confidence,
    NULL::text AS evidence_summary,
    NULL::jsonb AS metadata,
    NULL::timestamp with time zone AS created_at,
    NULL::timestamp with time zone AS updated_at,
    NULL::bigint AS link_count;

ALTER TABLE ONLY kardex.action_recommendations ALTER COLUMN id SET DEFAULT nextval('kardex.action_recommendations_id_seq'::regclass);

ALTER TABLE ONLY kardex.actions ALTER COLUMN id SET DEFAULT nextval('kardex.actions_id_seq'::regclass);

ALTER TABLE ONLY kardex.boundaries ALTER COLUMN id SET DEFAULT nextval('kardex.boundaries_id_seq'::regclass);

ALTER TABLE ONLY kardex.channels ALTER COLUMN id SET DEFAULT nextval('kardex.channels_id_seq'::regclass);

ALTER TABLE ONLY kardex.claims ALTER COLUMN id SET DEFAULT nextval('kardex.claims_id_seq'::regclass);

ALTER TABLE ONLY kardex.communication_deviations ALTER COLUMN deviation_id SET DEFAULT nextval('kardex.communication_deviations_deviation_id_seq'::regclass);

ALTER TABLE ONLY kardex.communication_patterns ALTER COLUMN id SET DEFAULT nextval('kardex.communication_patterns_id_seq'::regclass);

ALTER TABLE ONLY kardex.contact_merge_audit ALTER COLUMN id SET DEFAULT nextval('kardex.contact_merge_audit_id_seq'::regclass);

ALTER TABLE ONLY kardex.contact_merge_candidates ALTER COLUMN id SET DEFAULT nextval('kardex.contact_merge_candidates_id_seq'::regclass);

ALTER TABLE ONLY kardex.contacts ALTER COLUMN id SET DEFAULT nextval('kardex.contacts_id_seq'::regclass);

ALTER TABLE ONLY kardex.context_packs ALTER COLUMN id SET DEFAULT nextval('kardex.context_packs_id_seq'::regclass);

ALTER TABLE ONLY kardex.conversation_episodes ALTER COLUMN id SET DEFAULT nextval('kardex.conversation_episodes_id_seq'::regclass);

ALTER TABLE ONLY kardex.corrections ALTER COLUMN id SET DEFAULT nextval('kardex.corrections_id_seq'::regclass);

ALTER TABLE ONLY kardex.disclosure_transitions ALTER COLUMN id SET DEFAULT nextval('kardex.disclosure_transitions_id_seq'::regclass);

ALTER TABLE ONLY kardex.entities ALTER COLUMN id SET DEFAULT nextval('kardex.entities_id_seq'::regclass);

ALTER TABLE ONLY kardex.events ALTER COLUMN id SET DEFAULT nextval('kardex.events_id_seq'::regclass);

ALTER TABLE ONLY kardex.evidence ALTER COLUMN id SET DEFAULT nextval('kardex.evidence_id_seq'::regclass);

ALTER TABLE ONLY kardex.extraction_runs ALTER COLUMN id SET DEFAULT nextval('kardex.extraction_runs_id_seq'::regclass);

ALTER TABLE ONLY kardex.health_notes ALTER COLUMN id SET DEFAULT nextval('kardex.health_notes_id_seq'::regclass);

ALTER TABLE ONLY kardex.identity_clusters ALTER COLUMN id SET DEFAULT nextval('kardex.identity_clusters_id_seq'::regclass);

ALTER TABLE ONLY kardex.identity_links ALTER COLUMN id SET DEFAULT nextval('kardex.identity_links_id_seq'::regclass);

ALTER TABLE ONLY kardex.identity_mentions ALTER COLUMN id SET DEFAULT nextval('kardex.identity_mentions_id_seq'::regclass);

ALTER TABLE ONLY kardex.journal_entries ALTER COLUMN id SET DEFAULT nextval('kardex.journal_entries_id_seq'::regclass);

ALTER TABLE ONLY kardex.media ALTER COLUMN id SET DEFAULT nextval('kardex.media_id_seq'::regclass);

ALTER TABLE ONLY kardex.messages ALTER COLUMN id SET DEFAULT nextval('kardex.messages_id_seq'::regclass);

ALTER TABLE ONLY kardex.open_loops ALTER COLUMN id SET DEFAULT nextval('kardex.open_loops_id_seq'::regclass);

ALTER TABLE ONLY kardex.preferences ALTER COLUMN id SET DEFAULT nextval('kardex.preferences_id_seq'::regclass);

ALTER TABLE ONLY kardex.psychological_claims ALTER COLUMN id SET DEFAULT nextval('kardex.psychological_claims_id_seq'::regclass);

ALTER TABLE ONLY kardex.raw_items ALTER COLUMN id SET DEFAULT nextval('kardex.raw_items_id_seq'::regclass);

ALTER TABLE ONLY kardex.recommendations ALTER COLUMN id SET DEFAULT nextval('kardex.recommendations_id_seq'::regclass);

ALTER TABLE ONLY kardex.rel_disclosure_transitions ALTER COLUMN id SET DEFAULT nextval('kardex.rel_disclosure_transitions_id_seq'::regclass);

ALTER TABLE ONLY kardex.relationship_events ALTER COLUMN id SET DEFAULT nextval('kardex.relationship_events_id_seq'::regclass);

ALTER TABLE ONLY kardex.relationship_metrics ALTER COLUMN id SET DEFAULT nextval('kardex.relationship_metrics_id_seq'::regclass);

ALTER TABLE ONLY kardex.relationships ALTER COLUMN id SET DEFAULT nextval('kardex.relationships_id_seq'::regclass);

ALTER TABLE ONLY kardex.social_graph ALTER COLUMN id SET DEFAULT nextval('kardex.social_graph_id_seq'::regclass);

ALTER TABLE ONLY kardex.source_threads ALTER COLUMN id SET DEFAULT nextval('kardex.source_threads_id_seq'::regclass);

ALTER TABLE ONLY kardex.style_profiles ALTER COLUMN id SET DEFAULT nextval('kardex.style_profiles_id_seq'::regclass);

ALTER TABLE ONLY kardex.sync_state ALTER COLUMN id SET DEFAULT nextval('kardex.sync_state_id_seq'::regclass);

ALTER TABLE ONLY kardex.action_recommendations
    ADD CONSTRAINT action_recommendations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.actions
    ADD CONSTRAINT actions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.boundaries
    ADD CONSTRAINT boundaries_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.channels
    ADD CONSTRAINT channels_contact_id_platform_platform_id_key UNIQUE (contact_id, platform, platform_id);

ALTER TABLE ONLY kardex.channels
    ADD CONSTRAINT channels_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.claim_evidence
    ADD CONSTRAINT claim_evidence_pkey PRIMARY KEY (claim_id, evidence_id, role);

ALTER TABLE ONLY kardex.claims
    ADD CONSTRAINT claims_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.communication_deviations
    ADD CONSTRAINT communication_deviations_entity_id_metric_detected_on_key UNIQUE (entity_id, metric, detected_on);

ALTER TABLE ONLY kardex.communication_deviations
    ADD CONSTRAINT communication_deviations_pkey PRIMARY KEY (deviation_id);

ALTER TABLE ONLY kardex.communication_patterns
    ADD CONSTRAINT communication_patterns_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.contact_merge_audit
    ADD CONSTRAINT contact_merge_audit_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.contact_merge_candidates
    ADD CONSTRAINT contact_merge_candidates_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.contact_merge_candidates
    ADD CONSTRAINT contact_merge_candidates_source_contact_id_target_contact_i_key UNIQUE (source_contact_id, target_contact_id, reason);

ALTER TABLE ONLY kardex.contacts
    ADD CONSTRAINT contacts_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.context_packs
    ADD CONSTRAINT context_packs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.conversation_episodes
    ADD CONSTRAINT conversation_episodes_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.corrections
    ADD CONSTRAINT corrections_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.disclosure_transitions
    ADD CONSTRAINT disclosure_transitions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.entities
    ADD CONSTRAINT entities_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.episode_items
    ADD CONSTRAINT episode_items_pkey PRIMARY KEY (episode_id, raw_item_id, role);

ALTER TABLE ONLY kardex.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.evidence
    ADD CONSTRAINT evidence_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.extraction_runs
    ADD CONSTRAINT extraction_runs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.health_notes
    ADD CONSTRAINT health_notes_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.hindsight_sync_state
    ADD CONSTRAINT hindsight_sync_state_pkey PRIMARY KEY (table_name);

ALTER TABLE ONLY kardex.identity_clusters
    ADD CONSTRAINT identity_clusters_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.identity_links
    ADD CONSTRAINT identity_links_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.identity_links
    ADD CONSTRAINT identity_links_source_identifier_type_normalized_value_key UNIQUE (source, identifier_type, normalized_value);

ALTER TABLE ONLY kardex.identity_mentions
    ADD CONSTRAINT identity_mentions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.journal_entries
    ADD CONSTRAINT journal_entries_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.media
    ADD CONSTRAINT media_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.messages
    ADD CONSTRAINT messages_source_source_message_id_key UNIQUE (source, source_message_id);

ALTER TABLE ONLY kardex.open_loops
    ADD CONSTRAINT open_loops_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.preferences
    ADD CONSTRAINT preferences_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.psychological_claims
    ADD CONSTRAINT psychological_claims_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.raw_items
    ADD CONSTRAINT raw_items_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.raw_items
    ADD CONSTRAINT raw_items_source_external_id_key UNIQUE (source, external_id);

ALTER TABLE ONLY kardex.recommendations
    ADD CONSTRAINT recommendations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.rel_disclosure_transitions
    ADD CONSTRAINT rel_disclosure_transitions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.relationship_baselines
    ADD CONSTRAINT relationship_baselines_pkey PRIMARY KEY (entity_id, window_name);

ALTER TABLE ONLY kardex.relationship_events
    ADD CONSTRAINT relationship_events_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.relationship_evidence
    ADD CONSTRAINT relationship_evidence_pkey PRIMARY KEY (relationship_id, evidence_id);

ALTER TABLE ONLY kardex.relationship_metrics
    ADD CONSTRAINT relationship_metrics_contact_id_metric_name_metric_period_p_key UNIQUE (contact_id, metric_name, metric_period, period_start, period_end);

ALTER TABLE ONLY kardex.relationship_metrics
    ADD CONSTRAINT relationship_metrics_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.relationships
    ADD CONSTRAINT relationships_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.social_graph
    ADD CONSTRAINT social_graph_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.source_threads
    ADD CONSTRAINT source_threads_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.source_threads
    ADD CONSTRAINT source_threads_source_external_thread_id_key UNIQUE (source, external_thread_id);

ALTER TABLE ONLY kardex.style_profiles
    ADD CONSTRAINT style_profiles_contact_id_owner_key UNIQUE (contact_id, owner);

ALTER TABLE ONLY kardex.style_profiles
    ADD CONSTRAINT style_profiles_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.sync_state
    ADD CONSTRAINT sync_state_pkey PRIMARY KEY (id);

ALTER TABLE ONLY kardex.sync_state
    ADD CONSTRAINT sync_state_source_source_id_key UNIQUE (source, source_id);

CREATE INDEX deviations_open ON kardex.communication_deviations USING btree (detected_on DESC) WHERE (acknowledged_at IS NULL);

CREATE INDEX idx_action_recs_contact ON kardex.action_recommendations USING btree (contact_id, status, priority);

CREATE INDEX idx_actions_contact ON kardex.actions USING btree (contact_id, status);

CREATE INDEX idx_actions_pending ON kardex.actions USING btree (contact_id, due_date) WHERE (status = 'pending'::text);

CREATE INDEX idx_boundaries_contact ON kardex.boundaries USING btree (contact_id, boundary_type, status);

CREATE INDEX idx_channels_contact ON kardex.channels USING btree (contact_id);

CREATE UNIQUE INDEX idx_channels_platform_platform_id_unique ON kardex.channels USING btree (platform, platform_id) WHERE ((platform_id IS NOT NULL) AND (platform_id <> ''::text));

CREATE INDEX idx_claim_evidence_evidence ON kardex.claim_evidence USING btree (evidence_id);

CREATE INDEX idx_claims_confidence ON kardex.claims USING btree (confidence DESC);

CREATE INDEX idx_claims_contact_type ON kardex.claims USING btree (contact_id, claim_type, status);

CREATE INDEX idx_claims_disclosure ON kardex.claims USING btree (contact_id, disclosure_state);

CREATE INDEX idx_claims_json ON kardex.claims USING gin (claim_json);

CREATE INDEX idx_claims_policy ON kardex.claims USING btree (contact_id, mention_policy);

CREATE INDEX idx_comm_patterns_contact ON kardex.communication_patterns USING btree (contact_id, pattern_type, status);

CREATE INDEX idx_contact_merge_audit_contacts ON kardex.contact_merge_audit USING btree (source_contact_id, target_contact_id, created_at DESC);

CREATE INDEX idx_contact_merge_candidates_status ON kardex.contact_merge_candidates USING btree (status, confidence DESC);

CREATE INDEX idx_contacts_canonical_name ON kardex.contacts USING btree (canonical_name);

CREATE INDEX idx_contacts_entity ON kardex.contacts USING btree (entity_id);

CREATE INDEX idx_contacts_handles ON kardex.contacts USING gin (handles);

CREATE INDEX idx_contacts_identity_status ON kardex.contacts USING btree (identity_status);

CREATE INDEX idx_contacts_phones ON kardex.contacts USING gin (phone_numbers);

CREATE UNIQUE INDEX idx_contacts_uuid ON kardex.contacts USING btree (contact_uuid);

CREATE INDEX idx_context_packs_contact ON kardex.context_packs USING btree (contact_id, pack_type, created_at DESC);

CREATE INDEX idx_corrections_contact ON kardex.corrections USING btree (contact_id, status);

CREATE INDEX idx_corrections_type ON kardex.corrections USING btree (correction_type, status);

CREATE INDEX idx_entities_normname_trgm ON kardex.entities USING gin (normalized_name public.gin_trgm_ops);

CREATE INDEX idx_entities_type ON kardex.entities USING btree (entity_type);

CREATE INDEX idx_episode_items_raw ON kardex.episode_items USING btree (raw_item_id);

CREATE INDEX idx_episodes_contact_time ON kardex.conversation_episodes USING btree (contact_id, start_at, end_at);

CREATE INDEX idx_episodes_importance ON kardex.conversation_episodes USING btree (contact_id, importance DESC);

CREATE INDEX idx_events_contact ON kardex.events USING btree (contact_id, event_date);

CREATE INDEX idx_events_upcoming ON kardex.events USING btree (event_date) WHERE (status = 'upcoming'::text);

CREATE INDEX idx_evidence_contact_ts ON kardex.evidence USING btree (contact_id, "timestamp" DESC);

CREATE INDEX idx_evidence_media ON kardex.evidence USING btree (media_id);

CREATE INDEX idx_evidence_message ON kardex.evidence USING btree (message_id);

CREATE INDEX idx_extraction_runs_contact ON kardex.extraction_runs USING btree (contact_id, started_at DESC);

CREATE INDEX idx_extraction_runs_stage ON kardex.extraction_runs USING btree (stage, status);

CREATE INDEX idx_health_notes_contact ON kardex.health_notes USING btree (contact_id, note_type, status);

CREATE INDEX idx_identity_clusters_contact ON kardex.identity_clusters USING btree (canonical_contact_id);

CREATE INDEX idx_identity_clusters_status ON kardex.identity_clusters USING btree (status, confidence DESC);

CREATE INDEX idx_identity_links_cluster ON kardex.identity_links USING btree (identity_cluster_id);

CREATE INDEX idx_identity_links_contact ON kardex.identity_links USING btree (contact_id);

CREATE INDEX idx_identity_links_value ON kardex.identity_links USING btree (identifier_type, normalized_value);

CREATE INDEX idx_identity_mentions_contact ON kardex.identity_mentions USING btree (contact_id, mention_type);

CREATE INDEX idx_identity_mentions_text ON kardex.identity_mentions USING btree (lower(mention_text));

CREATE INDEX idx_journal_contact ON kardex.journal_entries USING btree (contact_id);

CREATE INDEX idx_journal_date ON kardex.journal_entries USING btree (entry_date DESC);

CREATE INDEX idx_journal_emotional ON kardex.journal_entries USING gin (emotional_tags);

CREATE INDEX idx_journal_mood ON kardex.journal_entries USING btree (mood);

CREATE INDEX idx_journal_topics ON kardex.journal_entries USING gin (related_topics);

CREATE INDEX idx_journal_type ON kardex.journal_entries USING btree (entry_type);

CREATE INDEX idx_media_contact ON kardex.media USING btree (contact_id);

CREATE INDEX idx_media_type ON kardex.media USING btree (contact_id, media_type);

CREATE INDEX idx_media_unanalyzed ON kardex.media USING btree (is_analyzed) WHERE (NOT is_analyzed);

CREATE INDEX idx_messages_contact_ts ON kardex.messages USING btree (contact_id, "timestamp" DESC);

CREATE INDEX idx_messages_sender ON kardex.messages USING btree (contact_id, sender);

CREATE INDEX idx_messages_source ON kardex.messages USING btree (source, source_message_id);

CREATE INDEX idx_open_loops_contact ON kardex.open_loops USING btree (contact_id, status, priority);

CREATE INDEX idx_open_loops_deadline ON kardex.open_loops USING btree (deadline_at) WHERE (status = 'open'::text);

CREATE INDEX idx_preferences_contact_category ON kardex.preferences USING btree (contact_id, category, status);

CREATE INDEX idx_psych_claims_contact_dim ON kardex.psychological_claims USING btree (contact_id, dimension);

CREATE INDEX idx_raw_items_contact_ts ON kardex.raw_items USING btree (contact_id, "timestamp" DESC);

CREATE INDEX idx_raw_items_hash ON kardex.raw_items USING btree (content_hash);

CREATE INDEX idx_raw_items_source ON kardex.raw_items USING btree (source, external_id);

CREATE INDEX idx_recommendations_contact ON kardex.recommendations USING btree (contact_id, item_type, status);

CREATE INDEX idx_rel_source ON kardex.relationships USING btree (source_entity_id);

CREATE INDEX idx_rel_source_status ON kardex.relationships USING btree (source_entity_id, status);

CREATE INDEX idx_rel_status ON kardex.relationships USING btree (status);

CREATE INDEX idx_rel_target ON kardex.relationships USING btree (target_entity_id);

CREATE INDEX idx_rel_target_status ON kardex.relationships USING btree (target_entity_id, status);

CREATE INDEX idx_rel_type ON kardex.relationships USING btree (relationship_type);

CREATE INDEX idx_relationship_events_contact_date ON kardex.relationship_events USING btree (contact_id, date_start DESC);

CREATE INDEX idx_relationship_events_type ON kardex.relationship_events USING btree (contact_id, event_type, importance DESC);

CREATE INDEX idx_relationship_metrics_contact ON kardex.relationship_metrics USING btree (contact_id, metric_name, period_start DESC);

CREATE INDEX idx_social_graph_contact ON kardex.social_graph USING btree (contact_id, relationship_to_contact, status);

CREATE INDEX idx_source_threads_contact ON kardex.source_threads USING btree (contact_id);

CREATE INDEX idx_source_threads_source ON kardex.source_threads USING btree (source, external_thread_id);

CREATE INDEX idx_style_profiles_contact ON kardex.style_profiles USING btree (contact_id, owner);

CREATE INDEX idx_sync_source ON kardex.sync_state USING btree (source, status);

CREATE INDEX idx_transitions_claim ON kardex.disclosure_transitions USING btree (claim_id);

CREATE UNIQUE INDEX uq_entities_type_normname ON kardex.entities USING btree (entity_type, normalized_name);

CREATE UNIQUE INDEX uq_relationships_triplet_active ON kardex.relationships USING btree (source_entity_id, target_entity_id, relationship_type) WHERE (status = ANY (ARRAY['proposed'::text, 'confirmed'::text]));

CREATE OR REPLACE VIEW kardex.v_claims_without_evidence AS
 SELECT c.id,
    c.contact_id,
    c.claim_type,
    c.category,
    c.claim,
    c.claim_json,
    c.status,
    c.confidence,
    c.stability,
    c.valid_from,
    c.valid_to,
    c.extraction_method,
    c.extraction_run_id,
    c.supersedes_claim_id,
    c.metadata,
    c.created_at,
    c.updated_at
   FROM (kardex.claims c
     LEFT JOIN kardex.claim_evidence ce ON ((ce.claim_id = c.id)))
  WHERE (c.status = 'active'::text)
  GROUP BY c.id
 HAVING (count(ce.evidence_id) = 0);

CREATE OR REPLACE VIEW kardex.v_unresolved_identities AS
 SELECT ic.id,
    ic.canonical_contact_id,
    ic.status,
    ic.cluster_label,
    ic.confidence,
    ic.evidence_summary,
    ic.metadata,
    ic.created_at,
    ic.updated_at,
    count(il.id) AS link_count
   FROM (kardex.identity_clusters ic
     LEFT JOIN kardex.identity_links il ON ((il.identity_cluster_id = ic.id)))
  WHERE (ic.status = ANY (ARRAY['unresolved'::text, 'candidate_merge'::text]))
  GROUP BY ic.id
  ORDER BY ic.confidence DESC, ic.updated_at DESC;

ALTER TABLE ONLY kardex.action_recommendations
    ADD CONSTRAINT action_recommendations_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.action_recommendations
    ADD CONSTRAINT action_recommendations_extraction_run_id_fkey FOREIGN KEY (extraction_run_id) REFERENCES kardex.extraction_runs(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.action_recommendations
    ADD CONSTRAINT action_recommendations_open_loop_id_fkey FOREIGN KEY (open_loop_id) REFERENCES kardex.open_loops(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.actions
    ADD CONSTRAINT actions_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.boundaries
    ADD CONSTRAINT boundaries_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES kardex.claims(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.boundaries
    ADD CONSTRAINT boundaries_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.channels
    ADD CONSTRAINT channels_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.claim_evidence
    ADD CONSTRAINT claim_evidence_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES kardex.claims(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.claim_evidence
    ADD CONSTRAINT claim_evidence_evidence_id_fkey FOREIGN KEY (evidence_id) REFERENCES kardex.evidence(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.claims
    ADD CONSTRAINT claims_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.claims
    ADD CONSTRAINT claims_extraction_run_id_fkey FOREIGN KEY (extraction_run_id) REFERENCES kardex.extraction_runs(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.claims
    ADD CONSTRAINT claims_supersedes_claim_id_fkey FOREIGN KEY (supersedes_claim_id) REFERENCES kardex.claims(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.communication_deviations
    ADD CONSTRAINT communication_deviations_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES core.entities(entity_id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.communication_patterns
    ADD CONSTRAINT communication_patterns_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES kardex.claims(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.communication_patterns
    ADD CONSTRAINT communication_patterns_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.contact_merge_audit
    ADD CONSTRAINT contact_merge_audit_source_contact_id_fkey FOREIGN KEY (source_contact_id) REFERENCES kardex.contacts(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.contact_merge_audit
    ADD CONSTRAINT contact_merge_audit_target_contact_id_fkey FOREIGN KEY (target_contact_id) REFERENCES kardex.contacts(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.contact_merge_candidates
    ADD CONSTRAINT contact_merge_candidates_source_contact_id_fkey FOREIGN KEY (source_contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.contact_merge_candidates
    ADD CONSTRAINT contact_merge_candidates_target_contact_id_fkey FOREIGN KEY (target_contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.contacts
    ADD CONSTRAINT contacts_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES kardex.entities(id);

ALTER TABLE ONLY kardex.context_packs
    ADD CONSTRAINT context_packs_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.conversation_episodes
    ADD CONSTRAINT conversation_episodes_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.conversation_episodes
    ADD CONSTRAINT conversation_episodes_extraction_run_id_fkey FOREIGN KEY (extraction_run_id) REFERENCES kardex.extraction_runs(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.corrections
    ADD CONSTRAINT corrections_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.disclosure_transitions
    ADD CONSTRAINT disclosure_transitions_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES kardex.claims(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.disclosure_transitions
    ADD CONSTRAINT disclosure_transitions_trigger_evidence_id_fkey FOREIGN KEY (trigger_evidence_id) REFERENCES kardex.evidence(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.entities
    ADD CONSTRAINT entities_merged_into_fkey FOREIGN KEY (merged_into) REFERENCES kardex.entities(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.episode_items
    ADD CONSTRAINT episode_items_episode_id_fkey FOREIGN KEY (episode_id) REFERENCES kardex.conversation_episodes(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.episode_items
    ADD CONSTRAINT episode_items_raw_item_id_fkey FOREIGN KEY (raw_item_id) REFERENCES kardex.raw_items(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.events
    ADD CONSTRAINT events_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.evidence
    ADD CONSTRAINT evidence_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.evidence
    ADD CONSTRAINT evidence_extraction_run_id_fkey FOREIGN KEY (extraction_run_id) REFERENCES kardex.extraction_runs(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.evidence
    ADD CONSTRAINT evidence_media_id_fkey FOREIGN KEY (media_id) REFERENCES kardex.media(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.evidence
    ADD CONSTRAINT evidence_message_id_fkey FOREIGN KEY (message_id) REFERENCES kardex.messages(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.evidence
    ADD CONSTRAINT evidence_raw_item_id_fkey FOREIGN KEY (raw_item_id) REFERENCES kardex.raw_items(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.extraction_runs
    ADD CONSTRAINT extraction_runs_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.source_threads
    ADD CONSTRAINT fk_source_threads_identity_cluster FOREIGN KEY (identity_cluster_id) REFERENCES kardex.identity_clusters(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.health_notes
    ADD CONSTRAINT health_notes_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES kardex.claims(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.health_notes
    ADD CONSTRAINT health_notes_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.identity_clusters
    ADD CONSTRAINT identity_clusters_canonical_contact_id_fkey FOREIGN KEY (canonical_contact_id) REFERENCES kardex.contacts(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.identity_links
    ADD CONSTRAINT identity_links_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.identity_links
    ADD CONSTRAINT identity_links_identity_cluster_id_fkey FOREIGN KEY (identity_cluster_id) REFERENCES kardex.identity_clusters(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.identity_mentions
    ADD CONSTRAINT identity_mentions_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.identity_mentions
    ADD CONSTRAINT identity_mentions_message_id_fkey FOREIGN KEY (message_id) REFERENCES kardex.messages(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.identity_mentions
    ADD CONSTRAINT identity_mentions_raw_item_id_fkey FOREIGN KEY (raw_item_id) REFERENCES kardex.raw_items(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.journal_entries
    ADD CONSTRAINT journal_entries_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id);

ALTER TABLE ONLY kardex.media
    ADD CONSTRAINT media_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.media
    ADD CONSTRAINT media_message_id_fkey FOREIGN KEY (message_id) REFERENCES kardex.messages(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.messages
    ADD CONSTRAINT messages_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES kardex.channels(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.messages
    ADD CONSTRAINT messages_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.open_loops
    ADD CONSTRAINT open_loops_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES kardex.claims(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.open_loops
    ADD CONSTRAINT open_loops_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.open_loops
    ADD CONSTRAINT open_loops_episode_id_fkey FOREIGN KEY (episode_id) REFERENCES kardex.conversation_episodes(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.preferences
    ADD CONSTRAINT preferences_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES kardex.claims(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.preferences
    ADD CONSTRAINT preferences_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id);

ALTER TABLE ONLY kardex.psychological_claims
    ADD CONSTRAINT psychological_claims_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES kardex.claims(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.psychological_claims
    ADD CONSTRAINT psychological_claims_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id);

ALTER TABLE ONLY kardex.psychological_claims
    ADD CONSTRAINT psychological_claims_extraction_run_id_fkey FOREIGN KEY (extraction_run_id) REFERENCES kardex.extraction_runs(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.raw_items
    ADD CONSTRAINT raw_items_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.raw_items
    ADD CONSTRAINT raw_items_media_id_fkey FOREIGN KEY (media_id) REFERENCES kardex.media(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.raw_items
    ADD CONSTRAINT raw_items_message_id_fkey FOREIGN KEY (message_id) REFERENCES kardex.messages(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.raw_items
    ADD CONSTRAINT raw_items_source_thread_id_fkey FOREIGN KEY (source_thread_id) REFERENCES kardex.source_threads(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.recommendations
    ADD CONSTRAINT recommendations_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES kardex.claims(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.recommendations
    ADD CONSTRAINT recommendations_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.rel_disclosure_transitions
    ADD CONSTRAINT rel_disclosure_transitions_relationship_id_fkey FOREIGN KEY (relationship_id) REFERENCES kardex.relationships(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.rel_disclosure_transitions
    ADD CONSTRAINT rel_disclosure_transitions_trigger_evidence_id_fkey FOREIGN KEY (trigger_evidence_id) REFERENCES kardex.evidence(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.relationship_baselines
    ADD CONSTRAINT relationship_baselines_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES core.entities(entity_id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.relationship_events
    ADD CONSTRAINT relationship_events_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.relationship_events
    ADD CONSTRAINT relationship_events_episode_id_fkey FOREIGN KEY (episode_id) REFERENCES kardex.conversation_episodes(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.relationship_events
    ADD CONSTRAINT relationship_events_extraction_run_id_fkey FOREIGN KEY (extraction_run_id) REFERENCES kardex.extraction_runs(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.relationship_evidence
    ADD CONSTRAINT relationship_evidence_evidence_id_fkey FOREIGN KEY (evidence_id) REFERENCES kardex.evidence(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.relationship_evidence
    ADD CONSTRAINT relationship_evidence_relationship_id_fkey FOREIGN KEY (relationship_id) REFERENCES kardex.relationships(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.relationship_metrics
    ADD CONSTRAINT relationship_metrics_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.relationship_metrics
    ADD CONSTRAINT relationship_metrics_extraction_run_id_fkey FOREIGN KEY (extraction_run_id) REFERENCES kardex.extraction_runs(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.relationships
    ADD CONSTRAINT relationships_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES kardex.claims(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.relationships
    ADD CONSTRAINT relationships_source_entity_id_fkey FOREIGN KEY (source_entity_id) REFERENCES kardex.entities(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.relationships
    ADD CONSTRAINT relationships_supersedes_rel_id_fkey FOREIGN KEY (supersedes_rel_id) REFERENCES kardex.relationships(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.relationships
    ADD CONSTRAINT relationships_target_entity_id_fkey FOREIGN KEY (target_entity_id) REFERENCES kardex.entities(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.social_graph
    ADD CONSTRAINT social_graph_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES kardex.claims(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.social_graph
    ADD CONSTRAINT social_graph_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.source_threads
    ADD CONSTRAINT source_threads_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES kardex.channels(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.source_threads
    ADD CONSTRAINT source_threads_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.style_profiles
    ADD CONSTRAINT style_profiles_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE CASCADE;

ALTER TABLE ONLY kardex.style_profiles
    ADD CONSTRAINT style_profiles_extraction_run_id_fkey FOREIGN KEY (extraction_run_id) REFERENCES kardex.extraction_runs(id) ON DELETE SET NULL;

ALTER TABLE ONLY kardex.sync_state
    ADD CONSTRAINT sync_state_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES kardex.contacts(id) ON DELETE SET NULL;
    $ddl$;
  end if;
end $walter_kardex_base$;
