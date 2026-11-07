# Mid-Turn User Feedback and Session Breakpoints

Session: 2026-07-02  
Trigger: Anti-progress signal during Skill Intelligence Loop execution. Agent emitted 90+ idempotent `session_search` calls with no query, then hit tool-call limit.

## Phenomenon

Mid-turn user messages (e.g., "You've reached the maximum number of tool-calling iterations. Please provide a final response...") are anti-progress signals. They are not requests to continue; they are requests to **stop and summarize**.

## Rule

When such a signal appears:
1. **STOP** all further tool calls immediately.
2. **Summarize** what was accomplished, what was not, and what blocked progress.
3. **Do NOT** launch new searches, retry scripts, or regress to earlier phases.
4. The session is functionally complete; treat the summary as the deliverable.

## Why This Matters for the Intelligence Loop

- The loop is designed to be autonomous. If it runs out of budget, that **is** a result.
- Producing a partial audit report is more valuable than spinning in an empty loop.
- Users receiving a mid-limit prompt are frustrated by lack of output; a summary is the correct output.