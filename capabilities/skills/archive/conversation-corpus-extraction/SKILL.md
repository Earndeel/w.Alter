---
name: conversation-corpus-extraction
description: Use before judging any chat corpus - pagination, negatives
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [beeper, kardex, corpus, pagination, media, forensics]
---

# Conversation Corpus Extraction

Class-level rules for pulling a COMPLETE chat history and making defensible claims about what it does/doesn't contain. Applies to any chat backend (Beeper API verified 2026-08); complements `beeper-messages` (API basics) and `contact-intelligence-systems` (Kardex schema).

## When to Use

Any task that fetches a conversation history, ingests it into Kardex, pulls attachments, or asserts presence/absence of information in a chat.

## Rule 1 — Pagination trap: 20 items/page regardless of `limit`

The Beeper messages endpoint caps every page at **20 items whatever `limit` says** (limit=50 returns 20).

Parameter verdicts (tested):
- `beforeSortKey=` / `afterSortKey=` / `sinceSortKey=` / `maxSortKey=` → silently IGNORED (return page 1 again)
- `cursor=<sortKey of the OLDEST item of previous page>` → the only parameter that actually paginates

```python
all_msgs, cursor = [], None
for _ in range(500):                      # safety cap
    d = fetch(f"{API}/v1/chats/{CHAT}/messages?limit=50" + (f"&cursor={cursor}" if cursor else ""))
    items = d.get("items", [])
    if not items: break
    all_msgs += items
    if not d.get("hasMore"): break
    cursor = items[-1]["sortKey"]
```

## Rule 2 — Negative claims require a complete corpus

A delta pull that makes ONE call grabs only the 20 newest messages; anything older is lost SILENTLY. Real cost (2026-08-23): a contact's full name sat in a 43-message block that a single-call delta skipped; the assistant told Monsieur the surname was unrecoverable and Monsieur corrected: « elle le dit dans nos derniers échanges, pourquoi tu ne l'as pas détecté ? ».

Before ANY negative statement ("never said X", "not in the conversation", "no mention of Y"):
1. paginate to exhaustion (`hasMore=false` or empty page)
2. verify total count vs expectation
3. only then conclude — and archive real negatives as `kardex.claims` type `osint_negative` (with queries tested) so future sessions don't re-burn searches

## Rule 3 — Idempotent Kardex ingestion

- Dedupe key: `source_message_id`. Insert pattern `INSERT ... SELECT ... WHERE NOT EXISTS`.
- Old rows may have `raw=NULL` → attachment metadata must be re-pulled from the API; the DB alone is insufficient.
- One SQL error rolls back the whole batch → fix then re-insert everything.
- Schema traps: no `relationship_events.event_date`, no `open_loops.loop_name`; `claims.claim` is NOT NULL (claim_json alone refuses).

## Rule 4 — Media retrieval

Attachment metadata points to Mac-local files; the API never serves media bytes. Media access runs over the existing Mac SSH route documented in the `beeper-messages` skill (media-access-pipeline reference) — reuse it rather than re-deriving commands here.

- Convert: `.webp` → PIL → png; `.mp4` (video-GIF) → `ffmpeg -vframes 1`.
- Vision efficiency: tile N images into one PIL grid (4×N, cells ~360×640) → one numbered-grid vision pass instead of N calls.
- Expectation setting: a contact's sent-media mix is typically ~60% stickers/cartoons, plus landscapes/pets/memes — face photos may be entirely absent. Say so rather than promising portraits.
- Deleted messages (`isDeleted:true`) have attachments purged at the API level; see Rule 5.

## Rule 5 — Evidence boundaries for relationship and sensitive-media analysis

When the corpus is romantic or emotionally sensitive:

- Keep separate notes for `observed`, `self-reported`, and `inferred`; date each claim and do not present an interpretation as a quote or fact.
- Treat affection, message volume, future language, sexual content, exclusivity, and relationship status as separate dimensions. Frequent contact does not prove commitment; sexual references do not prove infidelity; future talk does not prove a plan.
- Analyze both speakers and the interaction loop: withdrawal/approach, pressure, breakup tests, hidden expectations, repair, and whether repair changes the relationship structure. Do not diagnose from keywords or self-labels, and do not assign one-sided causality without evidence.
- For medical, reproductive, paternity, or financial media, enumerate visible metadata and compare every visible date or annotation for internal consistency. Do not infer authenticity, currentness, identity, paternity, diagnosis, or obligation from an image alone; request direct clarification before making a high-stakes recommendation.
- Treat Hindsight and prior analyses as dated context, not current fact. If historical context conflicts with live messages, label the conflict and prefer the live corpus.
- State the corpus boundary and the material unknowns in the final synthesis.

For the reusable relationship-analysis checklist and evidence matrix, see `references/relationship-analysis.md`.

## Rule 6 — Deleted-message forensics (Mac index.db)

- API purges attachments of deleted messages; the local cache file disappears too → content is definitively lost.
- `~/Library/Application Support/BeeperTexts/index.db`, table `mx_room_messages`, column `message` (JSON) retains metadata: timestamp, type, `isDeleted`, senderID — but `attachments:[]`.
- Query pattern: `SELECT datetime(timestamp/1000,'unixepoch'), type FROM mx_room_messages WHERE roomID='!<chatID>' AND isDeleted=1;`
- The `account.db` database holds state events only (~14 rows), NOT messages.
- Shell trap: Matrix event IDs start with `$` (eaten by shells) — filter by timestamp/sortKey, never a literal eventID.

## Rule 7 — OSINT round 2 after identity reveals

When a conversation later yields a real name, re-run web OSINT with it, but expect homonym floods for common names (verified: "Irene Hsu" → dozens of Taiwanese professionals, zero discriminable without hanzi + city). Record the null result as a claim so the dead end is documented, and keep prioritizing the conversation itself as the richest source.

## Related

- Comm metrics battery (15 patterns) + script: `/root/.hermes/skills/research/osint-public-profile-lookup/scripts/kardex_comm_metrics.py` — rerun after every ingestion.
- Public-web OSINT routes: `osint-public-profile-lookup` skill.
