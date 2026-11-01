# Conversational Harness Audit (Specialized Subtype)

Use this when auditing an LLM agent's conversational loop (ReAct pattern, tool-calling agents,
Telegram bots, voice assistants) — identify structural anti-patterns that make exchanges feel
artificial and propose the smallest testable refactor toward natural stateful conversation.

## Distinction from General Codebase Audit

A general audit scans the whole codebase (API, data layer, frontend, tests, CI/CD). A
conversational harness audit narrows to 3-5 core files and reads them in full, because the
anti-patterns live in the interaction between the ReAct loop, context management, system
prompt, and tool definitions — not spread across layers.

## Method

### 1. Identify the Core Files (cartography narrow)
- The agent entry point (where ReAct loop lives)
- The message builder (how context + user input → LLM payload)
- The system prompt builder (what instructions shape every response)
- The tool definitions (what actions the agent can take)
- The external handler (Telegram webhook, HTTP endpoint, voice gateway)

### 2. Read Them Completely
Do NOT read the first 200 lines of 20 files. Read these 3-5 files in full. The anti-patterns
are structural — they span hundreds of lines.

### 3. Identify Anti-Patterns with File:Line Evidence
Look for these specific categories (and any domain-specific variants):

| Category | Signal | Typical Evidence |
|----------|--------|-----------------|
| Context Amnesia | Hard truncation, aggressive summarization | `MAX_CONTEXT_MESSAGES = 8`, `context = []` after compaction |
| Stateless Processing | No conversation_id, no phase tracking | Flat state field, no phase machine |
| Prompt Over-specification | Mandatory structured output for every turn | `internal_thought` JSON + `<choices>` block required on simple "hello" |
| Tool Loop Contamination | Business logic in the ReAct loop instead of tools | Guard clauses, state checks in the loop body |
| Forced Interaction | Choices/buttons even when conversation is open | Every response carries inline keyboard markup |

### 4. Propose the Smallest Testable Refactor
- **Must be testable**: RED tests before GREEN
- **Must be small**: target <300 lines across <5 files
- **Must be safe**: zero breaking changes on external API or tools
- **Structure**: interface change → code change → DB migration → tests

### 5. Write RED Tests
Each anti-pattern gets a RED→GREEN test pair:
- RED: proves the current behavior is broken (the anti-pattern fires)
- GREEN: proves the refactor fixed it (the test passes after the change)

Tests should be in the project's own test framework and style (not generic).

## Report Structure

1. **Executive Summary** — 3 mechanisms in 3 sentences
2. **Per-Mechanism Section** — description, file:line table, concrete impact, RED test
3. **Refactor Proposal** — what changes, line count per file, migration needed
4. **Test Plan** — 3-4 RED→GREEN tests with assertions (pseudocode or actual framework)

## Verification
- [ ] 3-5 core files read in full (not skimmed)
- [ ] Each anti-pattern has 3+ file:line citations
- [ ] Each mechanism has a RED test that would FAIL on current code
- [ ] Refactor is under 300 lines, under 5 files, zero breaking changes
- [ ] Report is self-contained — no need to consult other docs to understand the findings
