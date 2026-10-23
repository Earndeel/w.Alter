# Search Loop Trap

Recurrence: Cron job session of the Skill Intelligence Loop (2026-06-25).
Background context was pointing toward a transition from search-based gap detection to a direct filesystem audit because previous session logs showed "null results" from `session_search` and external tool searches.

**The trap:** The agent got stuck repeatedly issuing `session_search`, `web_search`, and `tool_search` calls — despite consistent null results — and eventually emitted an *empty response* after tool execution, losing the execution context entirely.

**Correct behavior:**
1. Do not search the web, session DB, or tool indices to discover gaps. The local scripts (`skill_quality_audit.py` and `skill_gap_detector.py`) already cover quality grading and gap detection using local skill files and the session database.
2. Detect empty output during a run as a signal to immediately switch from search mode to executing the known local scripts.

**Embedded in SKILL.md:**
- Phase 2 now states "run the local script first."
- Pitfalls section captures "Search loop trap" and "Empty response trap."

Update whenever this pattern reappears to mark the rule as stronger.
