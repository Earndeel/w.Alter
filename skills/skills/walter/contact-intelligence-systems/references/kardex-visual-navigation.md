# Kardex Visual Navigation Pattern

Use this when Monsieur wants to browse Kardex visually.

## Recommendation

Keep PostgreSQL/Kardex as source of truth. Put a visual admin layer on top; do not move the canonical data into Notion.

Preferred path:

```text
PostgreSQL Kardex → Directus → private Tailscale UI
```

Alternative:

```text
PostgreSQL Kardex → NocoDB → Airtable-like grid UI
```

Notion role:

```text
Kardex → curated export/mirror → Notion
```

Notion is for readable dossiers and sharing, not identity resolution, message timelines, or merge validation.

## Required views

- Contacts list with search/filter
- Contact dossier
- Timeline of events/actions/messages
- Conversations with sender separation: Lucas vs contact
- Identity links / channels
- Pending merge candidates
- Open loops / follow-up actions
- Evidence/provenance per extracted fact

## Why not raw pgAdmin/DBeaver

They are good for database administration, not human navigation. Monsieur needs relational browsing, validation queues, and readable timelines, not tables with existential dread.

## Why Directus first

Directus maps naturally to PostgreSQL schemas, relationships, permissions, filters, and admin workflows. It is a better base for Kardex than a custom UI at the prototype stage, and more robust than forcing Notion to behave like a relational CRM.

## Safety rules

- Read/write via Kardex schema only; never let UI mutate Hindsight directly.
- Merge actions must be auditable and preferably write to `contact_merge_audit`.
- Same-name contacts must remain separate unless a strong identity signal exists.
- Sensitive conversations should be displayed with scoped access and not exported wholesale to Notion.