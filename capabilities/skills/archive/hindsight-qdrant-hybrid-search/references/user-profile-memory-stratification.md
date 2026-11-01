# User Profile / Hindsight Stratification

Use this pattern when designing W.Alter's long-term user understanding.

## Core rule

More available data does not mean more injected context. Separate canonical identity, current preferences, evidence history, and raw sensitive data.

## Layers

| Layer | Stores | Injection policy |
|---|---|---|
| USER.md / user store | Stable identity, current global preferences, durable communication rules, compact psychological/decision model | Always injected, aggressively compact |
| Hindsight / memory_facts | Evidence, episodes, previous versions, historical discussions, project history | Recall only when query/task needs it |
| Kardex | Contacts, messages, relationship history, contact-specific facts | Only when a person/conversation is relevant |
| Life data layer | Location, calendar, sleep, spending, health signals, device telemetry | Never raw by default; summarize into current user model or recall with explicit need |
| Skills | Reusable procedures and workflows | Loaded by task class |
| MEMORY.md | Environment/system conventions and stable tool quirks | Always injected if operationally important |

## Promotion rules

Promote to USER.md only if a fact changes the default behaviour of the assistant across most sessions:
- identity/history that will not change: origin, education, stable biography
- current preferences: communication style, decision support style, life/work preferences
- decision model: risk tolerance, common biases, triggers, patterns, what type of advice works

Keep in Hindsight only:
- session narratives
- one-off projects
- proofs/evidence for a user-profile claim
- old versions of preferences after they are superseded
- detailed medical/location/communication records

## Evolving preferences

Represent evolving preferences as current canonical values with evidence and timestamps, not as a pile of contradictions.

Recommended fields for future profile compiler:
- key
- current_value
- confidence
- updated_at
- evidence_ids
- supersedes
- privacy_class

Old preference versions should remain in Hindsight as evidence but should not be injected unless the task is about preference history.

## Psychological / decision profile

Allowed: practical hypotheses with confidence and evidence, e.g. decision patterns, biases, stress triggers, risk tolerance, attention patterns.

Avoid: definitive medical/psychiatric diagnosis without clinical basis. Phrase as observed patterns or hypotheses, not pathology labels.

## Injection discipline

Always injected should be small enough to fit in a few hundred tokens. Everything else should be reachable through recall, not shoved into the prompt. The model should know Monsieur well; it should not carry the entire attic into every room.