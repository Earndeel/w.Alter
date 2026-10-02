-- Monsieur's model knowledge (2026-10-02): video is not "number 1, number 2" — the right model depends on the
-- objective (premium cinematic, action, UGC, budget...), on the workflow a model demands (Seedance 2.5: reference
-- images + adapted prompting), on access (Omni 1.1 through Flow with the free monthly credits of Gemini AI Pro) and
-- on content policy (MiniMax H3: open weights, reputedly permissive). Ties between close models go to his affinity
-- (GPT-6 Luna, especially through the Codex subscription).
begin;
-- One fiche per model: Monsieur's own knowledge, never derived from leaderboards.
create table if not exists models.profiles (
    model_id        text primary key references models.canonical,
    strengths       text[] not null default '{}',   -- tags: action, ugc, cinematic, realism, value...
    weaknesses      text[] not null default '{}',
    workflow        jsonb not null default '[]',     -- ordered steps the orchestrator must plan before generating
    effort          text check (effort in ('direct', 'guided', 'workflow')),  -- how much preparation it needs
    access_note     text,                            -- e.g. free monthly credits through a subscription UI
    cost_note       text,
    content_policy  text check (content_policy in ('standard', 'permissive', 'unrestricted')),  -- overrides canonical
    note            text,
    source          text not null default 'monsieur',
    declared_at     timestamptz not null default now()
);

-- A favourite role is an objective: what it is for, and the words of a request that call for it.
alter table models.preferences add column if not exists label text;
alter table models.preferences add column if not exists description text;
alter table models.preferences add column if not exists signals text[] not null default '{}';
alter table models.preferences add column if not exists priority int not null default 0;  -- tie between roles

-- Close calls: inside the tie margin the model Monsieur prefers wins.
create table if not exists models.affinities (
    model_id    text not null references models.canonical,
    scope       text not null default '*',         -- task or '*'
    weight      int not null default 1,
    reason      text not null,
    declared_at timestamptz not null default now(),
    primary key (model_id, scope)
);

alter table models.canonical drop constraint if exists canonical_content_policy_check;
alter table models.canonical add constraint canonical_content_policy_check
    check (content_policy in ('standard', 'permissive', 'unrestricted'));

insert into models.schema_migrations (version) values ('006_profiles_roles_affinities') on conflict do nothing;
commit;
