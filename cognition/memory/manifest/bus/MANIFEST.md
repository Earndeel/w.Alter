# Walter bus

**Role.** Event delivery between modules. A producer emits an event (`skill.changed`, `turn.ended`, `session.ended`,
`memory.event`, `memory.derived`…); each consumer catches up from its cursor, then listens. Prefer it to timers or
file watchers for new reactions.

**Organisation.** PostgreSQL schema `bus` (events, per-consumer cursors, `bus.dead` for failed deliveries) with
`pg_notify('walter_bus')`; library `walter_memory/bus.py` (`emit` never raises, `Consumer.run` = catch-up then
LISTEN, `lag`).

**Interfaces.** Python only (`emit`, `Consumer`); no MCP tool. Producers include the runtime hook (turn and session
ends), the skills write door and Walter Memory processors; consumers include walter-skills and Walter Memory
(`memory.extract`, `memory.organic`).

**Live state**: consumer lag and dead letters through `walter_health` / `walter-memory health`; operations in the
RUNBOOK (« Bus Walter »).
