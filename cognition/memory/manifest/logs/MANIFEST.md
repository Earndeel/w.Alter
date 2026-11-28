# walter-logs

**Role.** The canonical journal of agent execution. Walter Memory keeps {{owner.address}}'s life; walter-logs keeps
the agents' work: messages, reasoning, tool calls with full arguments, full results, compaction summaries, model
selections — for the engine and every external agent session.

**Organisation.** Schema `walter_logs` (sessions, events), append-only, secrets masked at write, privacy class per
event, synchronised within seconds from each runtime.

**Tools**
- `logs_search(query, runtime, event_type, tool, since)`: words or an exact string (path, error, identifier); each
  hit carries `session#seq`.
- `logs_timeline(session, seq)`: what happened around it, in order; `logs_get(session, seq)`: one event in full.

Use it to find how a task was carried out, an exact command or error, or what preceded a compaction.
