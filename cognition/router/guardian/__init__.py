"""Guardian of the Walter Router: keeps the module working without the owner (2026-10-26), and since 2026-11-21 the
Router's one agent — « le Router » itself, Walter's sub-agent that maintains the module.

agent.py: its identity (agent.md, declared in contracts/maintenance.json) and its one door to Walter Engine. Its
missions: repair (checks.py detects, no model; run.py follows incidents and decides; repair.py hands what is ours to
the guardians' common repair agent, which opens with the same identity), advise (advice.py, instructions in
advice-brief.md), the plans watch (plan/watch.py), and Walter's `subagent` tool with agent "router". README.md
explains it in full.
"""
