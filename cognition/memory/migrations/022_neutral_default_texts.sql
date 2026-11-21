-- Walter Memory — default rows written by migrations name no person (2026-10-29, Walter Clean). 009 and 001 wrote
-- the first instance's owner into a connector description and a budget note; same meaning, neutral wording. A note
-- an instance has rewritten since is left alone.
update ingestion.connectors
   set description = 'Triage of new incoming events (messages, e-mails, calendar) by the decision model and the owner''s rules'
 where connector = 'triage';
update system.budgets set notes = 'Default; to be confirmed by the owner (D6).'
 where budget = 'recurring' and notes like 'Default; to be confirmed by %';
