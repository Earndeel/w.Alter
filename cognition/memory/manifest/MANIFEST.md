# Walter Memory

**Role.** The durable truth of {{owner.address}}'s life, usable by every agent: events from every source, knowledge
derived from them (always linked to its evidence), the social layer (Kardex: people, identities, relationships) and
durable tasks. It answers who / when / what with sources and dates, and records durable facts.

**Organisation.** Append-only canonical history (`core.events`); derived knowledge with provenance; Kardex (schema
`kardex`); full-text + semantic search index; connectors that feed it (Beeper, Google, agent sessions…); a single
write door (library or gateway). Privacy classes: `cloud_allowed`, `redacted_cloud`, `local_only`.

**Tools**
- `memory_context(query)`: a ready context block (people named, knowledge, original sources). The turn's
  `<walter-context>` block usually holds it already.
- `memory_search(query)`: knowledge + original evidence with source and date.
- `memory_events(text, source, event_type, thread_id, since, until, order="newest"|"oldest", event_id, limit)`: the
  exact text of canonical events; `event_type` exact (`message.received` = written to Monsieur) or a family
  (`message.*`), `source="people"` = his exchanges with humans on any channel (never W.Alter, an agent, a bot or a service: each event says `actor_kind`), `source="agents"` = with W.Alter and other agents; a newest-first read names any source not synchronised up to now (`freshness`); a conversation in order with `thread_id` (about a hundred messages per read, continue with
  `next`); `event_id` for one event in full. Messages with files carry `attachments` (voice-note transcript,
  document text…).
- `person_lookup(name)`: a person's card (identities, relationship, `thread_id` of their conversations).
- `memory_recall` / `memory_reflect`: synthesised facts / a sourced synthesis.
- `memory_retain(content)`: record a durable fact, never a secret or a transient log.
- `tasks_list(status, thread_id)`, `task_create(goal, entity_id | person, due_at, remind_at, draft, source)`,
  `task_update(task_id, status, progress, result, note)`: the owner's durable tasks; a task follows its thread, not
  the session, and can be resumed from another conversation or door. A draft is kept, never sent.

Recalled memories are dated snapshots: check the live state before asserting it, and cross-check an important
answer with the sources. Live state of the module: `walter_health` (memory score, connectors).
