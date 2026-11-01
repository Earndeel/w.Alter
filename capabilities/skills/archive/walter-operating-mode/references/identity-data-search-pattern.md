# Identity Data Search Pattern

When looking up user identity data (handles, usernames, account URLs, phone numbers), search in this exact order. Stop as soon as you find the data.

## Priority Order

1. **USER.md** (`~/.hermes/USER.md`) — always check first, per USER.md-wins rule
2. **Kardex contacts** — `kardex.contacts` table, `handles` JSONB column (structured, queryable)
3. **User Model profile_state** — `user_model.profile_state` (promoted signals with confidence)
4. **Memory facts** — `memory_facts` (structured facts, content column)
5. **Memory units** — `memory_units` (raw text, text + context columns)
6. **Hindsight signal_candidates** — `user_model.signal_candidates` (extracted but not yet promoted)
7. **Session history** — `session_search()` (last resort, ephemeral)

## How to Query Each

```sql
-- Docker container: hindsight-pg
-- User: hindsight | DB: hindsight

-- Kardex handles (most reliable)
SELECT canonical_name, handles FROM kardex.contacts
WHERE handles != '{}'::jsonb;

-- User Model profile_state
SELECT key, current_value, confidence FROM user_model.profile_state
WHERE key ILIKE '%handle%' OR key ILIKE '%social%' OR key ILIKE '%twitter%'
   OR current_value ILIKE '%x.com%' OR current_value ILIKE '%twitter%';

-- Memory facts
SELECT id, content FROM memory_facts
WHERE content ILIKE '%x.com/%' OR content ILIKE '%twitter.com%'
   OR content ILIKE '%handle%';

-- Memory units (broader text search)
SELECT id, text, context FROM memory_units
WHERE text ILIKE '%x.com/%' OR text ILIKE '%twitter.com/%';

-- Signal candidates
SELECT id, category, claim, evidence_quote FROM user_model.signal_candidates
WHERE claim ILIKE '%twitter%' OR claim ILIKE '%x.com%'
   OR claim ILIKE '%handle%' OR claim ILIKE '%social%';
```

## Pitfalls

- **Don't search ad-hoc**: the pattern above is exhaustive. If nothing found in all 7 layers, the data was never persisted.
- **Don't confuse "Monsieur uses Twitter" with "Monsieur's handle is @X"**: profile_state may record the activity without the identity. Check handles JSONB specifically.
- **Session history is ephemeral**: even if the handle was discussed yesterday, it may not be in session_search if the session was compacted or lost.
- **When data is missing after searching all layers**: tell the user directly, apologize, ask once, and persist immediately on receipt. Never ask twice in the same session.

## Container Access

```bash
docker exec hindsight-pg psql -U hindsight -d hindsight -t -c "QUERY"
```

The PG instance runs in Docker container `hindsight-pg`, user `hindsight`, database `hindsight`. There is no `memory` schema — the relevant schemas are `public` (memory_facts, memory_units) and `user_model`, `kardex`.

## Pitfalls (Addendum)

- **Always use `docker exec` for PG queries**: Direct `psql -h localhost` fails because PG is inside Docker. Use `docker exec hindsight-pg psql -U hindsight -d hindsight -t -c "QUERY"` instead. If `docker exec` fails, the container is down — report this as a connectivity issue, not "not found."
- **DB connectivity ≠ data absence**: If the PG container is unreachable, you cannot conclude the contact doesn't exist. Report: "DB connection failed, cannot verify Kardex contents" and suggest checking `docker ps | grep hindsight-pg`.
- **Beeper search is independent**: Even if PG is down, you can still search Beeper directly via API. Don't skip this step.
- **Session search is last resort**: It's ephemeral and may not contain historical data. Always try DB-backed sources first.
