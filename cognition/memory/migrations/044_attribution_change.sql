-- 2026-11-19 (owner: « corrige les attributions manifestement erronées déjà enregistrées, sans perdre leurs sources »):
-- a statement moved to its real subject (walter_memory/attribution.py) is recorded as op 'attribute' in the same
-- history as every other change (before/after attributes, tagged, undone by knowledge.revert). Additive, idempotent.
begin;
alter table core.derived_changes drop constraint if exists derived_changes_op_check;
alter table core.derived_changes add constraint derived_changes_op_check
    check (op in ('create', 'evidence', 'supersede', 'contest', 'advance', 'expire', 'link', 'restore', 'reconcile',
                  'attribute'));
commit;
