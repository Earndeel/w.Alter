# Identity Data Search Pattern

When looking up user identity data (handles, usernames, account URLs, phone numbers), search in this order. Stop as soon as you find the data.

## Priority Order

1. **USER.md** (`~/.hermes/memories/USER.md`): always check it first, per the USER.md-wins rule.
2. **Walter Memory**: memory recall/search (knowledge plus original evidence: messages, e-mails, agent conversations).
3. **Kardex**: person lookup; for structured handles, `kardex.contacts.handles` (JSONB).
4. **Historical, frozen layers** (read-only, may be stale):
   - `user_model.profile_state` and `user_model.signal_candidates`: the profile compiler that fed them was stopped on 2026-11-09, replaced by Walter Memory extraction.
   - `public.memory_units`: Hindsight artefact (Hindsight retired 2026-10-19).
5. **Session history**: `session_search()` (last resort, ephemeral).

## How to Query the SQL layers

```sql
-- Docker container: hindsight-pg | DB: hindsight (never print credentials)

-- Kardex handles
SELECT canonical_name, handles FROM kardex.contacts
WHERE handles != '{}'::jsonb;

-- Historical (frozen since 2026-11-09): promoted profile
SELECT key, current_value, confidence FROM user_model.profile_state
WHERE key ILIKE '%handle%' OR key ILIKE '%social%' OR key ILIKE '%twitter%'
   OR current_value ILIKE '%x.com%' OR current_value ILIKE '%twitter%';

-- Historical (frozen since 2026-11-09): candidates never promoted
SELECT id, category, claim, evidence_quote FROM user_model.signal_candidates
WHERE claim ILIKE '%twitter%' OR claim ILIKE '%x.com%'
   OR claim ILIKE '%handle%' OR claim ILIKE '%social%';
```

## Pitfalls

- **Live sources first.** Walter Memory and Kardex are live. A fact found only in `user_model` or `public` is old (from before 2026-11-09 or 2026-10-19): say so, then confirm it.
- **"Monsieur uses Twitter" is not "Monsieur's handle is @X".** A profile may record the activity without the identity, so check the handles specifically.
- **Session history is ephemeral.** A handle discussed yesterday may be missing from session_search if the session was compacted or lost.
- **When every layer comes back empty:** tell the user directly, ask once, and persist the answer immediately on receipt (Walter Memory, plus Kardex for a person). Never ask twice in the same session.
- **`public.memory_facts` no longer exists.** Do not query it.

## Container Access

```bash
docker exec hindsight-pg psql -U hindsight -d hindsight -t -c "QUERY"
```

- **Always use `docker exec` for PG queries.** If `docker exec` fails, the container is down: report a connectivity issue, not "not found".
- **DB connectivity ≠ data absence.** If PG is unreachable, you cannot conclude the data doesn't exist.
- **Beeper search is independent.** Even with PG down, you can still search Beeper directly through its API.
