---
name: kanban-suite
description: "High-throughput autonomous Kanban operations: coordinating orchestrators, task decomposition lanes, deep worker technical execution, and task board coordination."
version: 1.0.0
author: Orchestra Research
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Kanban, Autonomous, Orchestration, Worker, Coordination, Planning, Multi-Agent]
---

# Autonomous Kanban Operations & Coordination

A consolidated, class-level mastery skill for driving multi-agent autonomous engineering pipelines using task-board boards, lane tracking, orchestrator delegation, and focused worker execution.

---

## 1. Multi-Agent Kanban Coordination Architecture

Kanban boards are the perfect state managers for autonomous agents, preventing context contamination and structuring complex multi-step builds into digestible lanes.

```
       [ Kanban Board ]
              │
    ┌─────────▼─────────┐
    │    Orchestrator   │  <-- Decomposes goal, creates cards, plans roadmap
    └─────────┬─────────┘
              │ (dispatches)
    ┌─────────▼─────────┐
    │       Worker      │  <-- Technical execution, runs TDD/systematic-debugging
    └───────────────────┘
```

---

## 2. Orchestrator Role & Responsibilities

The **Orchestrator** is a high-level planner and coordinator. It must never perform raw code editing or test execution directly.

### Operational Protocols:
1. **Decomposition:** Split major epics into distinct, independent sub-cards with clear criteria.
2. **Dispatching:** Spawn subagents (Workers) using the `delegate_task` tool, passing all relevant file contexts, variables, and specs.
3. **Synthesis:** Combine worker reports into clean, comprehensive reviews.

---

## 3. Worker Role & Responsibilities

The **Worker** is a focused execution agent, optimized for coding, testing, and systematic repair.

### Operational Protocols:
1. **TDD Flow:** Write test cases before editing logic. Keep test loops clean and isolated.
2. **Safety Gates:** Run syntax and static analysis before compiling or pushing code.
3. **Structured Reports:** Return a clean self-report containing:
   - Modified paths
   - Test execution logs (successes and errors)
   - Unresolved issues or suggestions for downstream tasks

---

## Support Directory Map
- `references/orchestrator.md`: Architectural specification for the Kanban Orchestration layer, task states, board schemas, and communication protocols.
- `references/worker.md`: Execution guides for Worker agents, highlighting deep code work, CLI integration, and structured reporting.
