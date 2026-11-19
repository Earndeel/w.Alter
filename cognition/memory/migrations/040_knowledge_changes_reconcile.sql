-- 2026-11-19 (owner: « réconciliation des connaissances qui n'ont pas été reliées lors de leur extraction »): the pass
-- over existing knowledge (knowledge.reconcile_existing) records on an item that it was reconciled — kept as is, or
-- made the next version of an earlier item — as op 'reconcile' in the same history. Additive and idempotent.
begin;
alter table core.derived_changes drop constraint if exists derived_changes_op_check;
alter table core.derived_changes add constraint derived_changes_op_check
    check (op in ('create', 'evidence', 'supersede', 'contest', 'advance', 'expire', 'link', 'restore', 'reconcile'));
commit;
