-- Lot 1 of the organic consolidation loop (2026-11-19, owner mission « première boucle de consolidation organique »):
-- one write gate for knowledge (walter_memory/knowledge.py). Every change it makes to a knowledge item — a new
-- version, evidence added, an item replaced, contested, advanced in its lifecycle, expired — is recorded here with
-- the item's state before and after, the decision that caused it and its proof, so that the history of a piece of
-- knowledge can be read and a tagged run (a pilot) can be undone exactly, evidence on existing items included.
-- Additive and idempotent.
begin;

create table if not exists core.derived_changes (
    change_id   bigserial primary key,
    key         text not null unique,                -- idempotency: the same statement never changes an item twice
    at          timestamptz not null default now(),
    item_id     uuid not null,
    lineage_id  uuid,
    op          text not null check (op in ('create', 'evidence', 'supersede', 'contest', 'advance', 'expire',
                                            'link', 'restore')),
    verdict     text,                                -- the reconciliation verdict (Walter Decision memory.reconcile or deterministic)
    decided_by  text,                                -- deterministic:<rule> | decision:<need> | runplane | proof | owner
    confidence  real,
    tag         text,                                -- a tagged run (backfill pilot); null = live
    segment_id  uuid,
    generation  text,
    staged      boolean not null default false,     -- true = recorded only: the target is served knowledge and this run is a pilot
    before      jsonb,                               -- the changed fields before (null for create)
    after       jsonb,                               -- the changed fields after
    provenance  jsonb not null default '[]'::jsonb, -- core.provenance rows this change inserted (undone with it)
    proof       jsonb,                               -- for an advance: the proof ladder reading (claimed / executed / checked / confirmed / runplane)
    reason      text,
    reverted_at timestamptz
);
create index if not exists derived_changes_item_idx on core.derived_changes (item_id, change_id);
create index if not exists derived_changes_lineage_idx on core.derived_changes (lineage_id) where lineage_id is not null;
create index if not exists derived_changes_tag_idx on core.derived_changes (tag, change_id) where tag is not null;
comment on table core.derived_changes is 'History of knowledge items written by the single write gate (walter_memory.knowledge): one row per change with before/after images, verdict, decider and proof. A tagged run is undone from these rows (knowledge.revert). Append-only apart from reverted_at.';

-- Goal and action lifecycle (owner: demandé / accepté-planifié / en cours / annoncé terminé / vérifié / terminé / annulé / abandonné).
alter table core.derived_items drop constraint if exists derived_items_stage_check;
alter table core.derived_items add constraint derived_items_stage_check check (stage is null or stage = any (array[
    'requested', 'proposed', 'decided', 'accepted', 'in_progress', 'executed', 'verified', 'abandoned', 'cancelled',
    'open', 'done', 'stated']));
comment on column core.derived_items.stage is 'requested (asked) · proposed (agent, not settled) · decided (owner chose) · accepted (planned) · in_progress · executed (reported done: a report, not a proof) · verified (a proof: tool results, tests, owner confirmation) · done / cancelled / abandoned (closed) · open (commitment) · stated (no lifecycle)';

commit;
