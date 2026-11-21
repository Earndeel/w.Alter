---
name: walter-vm-resource-audit
description: Use when auditing W.Alter VM resource consumption, attributing CPU and memory to services, investigating duplicate model loads or orphan processes, and prioritizing optimizations without changing production.
---

# Read-only VM resource audit

## Establish boundaries

1. Read the applicable `CLAUDE.md` before inspecting the deployment. Confirm production services and any concurrent changes that must remain untouched.
2. Keep the audit read-only: do not kill processes, restart services, change timers, prune Docker, or modify configuration. Separate recommendations from authorized implementation.
3. Never print environment files, credentials, full request bodies, or personal records. Inspect code and aggregate metrics. Treat command lines, unit definitions, journals, and logs as potentially secret-bearing; select safe fields rather than dumping them wholesale.
4. Do not make paid model calls. A local embedding benchmark is a separate, resource-consuming experiment: run it only if necessary and distinguish it from passive observations.

## Inventory the machine and service ownership

Run:

```sh
uptime
nproc
free -m
df -h /
command -v pidstat top systemd-cgtop smem
systemctl list-units --type=service --state=running --no-pager
systemctl list-timers --all --no-pager
systemctl --failed --no-pager
```

From `/root`, query the Walter registry with bounded execution:

```sh
cd /root
timeout 60 walter status
timeout 120 walter deploy check --json
```

Extract module identifiers, runtime health, and service ownership; do not assume every enabled unit belongs to current production. In the audited deployment, native production was `walter-engine.service`, with Engine API on port 8895 and web on port 3080. Reconfirm rather than treating these as immutable.

For each relevant service, collect:

```sh
systemctl show walter-engine.service \
  -p Id -p ActiveState -p SubState -p MainPID -p ControlGroup \
  -p MemoryCurrent -p MemoryPeak -p MemorySwapCurrent \
  -p MemoryHigh -p MemoryMax -p CPUUsageNSec -p TasksCurrent \
  -p NRestarts -p ExecMainStartTimestamp
```

## Measure CPU over an interval

1. Sample for approximately ten minutes so short periodic jobs are represented. Record timestamps and the measurement window.
2. On cgroup v2, obtain each service's `ControlGroup` from systemd and read `/sys/fs/cgroup<ControlGroup>/cpu.stat`. Use the `usage_usec` delta:

   `CPU percent of one core = delta usage_usec / elapsed_seconds / 1000000 * 100`

3. Report this convention explicitly; divide by `nproc` only when expressing percentage of whole-machine capacity.
4. Sample individual PIDs as well when needed. A PID-only snapshot can miss timer jobs that exit between snapshots; cgroup counters preserve their CPU while that cgroup persists.
5. Detect disappearing or recreated cgroups and counter resets; do not calculate negative deltas or silently equate a replacement cgroup with the original.
6. Never sum parent and child cgroups as independent consumption. Attribute leaf services and show slice totals separately.
7. Label CPU spent by the audit's own helpers. Do not confuse cumulative lifetime CPU with interval utilization.

## Attribute memory rather than summing RSS

For each large cgroup, inspect:

```sh
cat /sys/fs/cgroup/system.slice/walter-engine.service/memory.current
cat /sys/fs/cgroup/system.slice/walter-engine.service/memory.swap.current
awk '$1=="anon" || $1=="file" || $1=="shmem"' \
  /sys/fs/cgroup/system.slice/walter-engine.service/memory.stat
cat /sys/fs/cgroup/system.slice/walter-engine.service/cgroup.procs
```

Substitute the actual `ControlGroup` path where different. For its PIDs, inspect `/proc/<pid>/status`, `/proc/<pid>/smaps_rollup`, and mapped-file names in `/proc/<pid>/maps`.

- Distinguish anonymous memory, file cache, shared memory, swap, RSS, and PSS. `memory.current` is not simply private process RAM.
- Use PSS and mapping evidence before claiming duplicate resident allocations; RSS can count shared pages repeatedly.
- Look for repeated local model loading in source code and configuration. Search the relevant module trees for `fastembed`, `onnxruntime`, `InferenceSession`, `TextEmbedding`, and `StaticModel.from_pretrained`.
- Relevant source locations in the audited deployment included `/walter/cognition/memory/walter_memory/search.py`, `/walter/capabilities/skills/walter_skills/ranker.py`, `/walter/capabilities/skills/config/walter-skills.toml`, and `/walter/cognition/context/walter_context/preflight/service.py`.
- Follow startup warm-up logic and imports: a service can load an embedding model indirectly without implementing embeddings itself.
- Do not promise that `mmap` alone will share anonymous inference allocations. Present a single embedding-serving process or validated shared mappings as implementation options requiring tests.

## Investigate non-service processes safely

1. Inspect populated scopes under `/sys/fs/cgroup/user.slice/user-0.slice/`, not just `system.slice`.
2. For suspicious PIDs, collect parent PID, start time, accumulated CPU, RSS, swap, executable path, working directory, and cgroup. Display only sanitized arguments if indispensable.
3. Use `pstree -p <pid>` and socket ownership from `ss -xpH` to establish callers before labeling a daemon abandoned. A long-lived CLI daemon may still serve current clients.
4. Check `/proc/<pid>/exe` for deleted executables after upgrades. Age or a deleted executable is evidence to investigate, not authorization to terminate.
5. Do not delete `~/.hermes` merely because Hermes itself is stopped: Router and autopilot components may still depend on it.

## Examine periodic work, queues, and database pressure

1. Correlate CPU bursts with `systemctl list-timers --all` and bounded journal windows. Distinguish historical deployment failures from current recurring failures.
2. Estimate daily overhead from measured cost per execution and timer frequency. Label projections separately from measured totals and avoid double-counting overlapping recommendations.
3. Inspect supervisor source for polling intervals, external SSH checks, and subprocess creation. Low steady-state CPU can hide frequent process starts.
4. Inspect Docker without pruning:

```sh
docker ps -a --size --filter status=exited \
  --format '{{.Names}}|{{.Size}}|{{.Status}}'
docker images --format '{{.Repository}}:{{.Tag}}|{{.Size}}|{{.ID}}'
```

5. For the observed PostgreSQL deployment, run aggregate, read-only queries through:

```sh
docker exec -i walter-pg psql -U walter -d walter \
  -X -A -P footer=off \
  -c 'select count(*) filter (where not granted) as waiting, count(*) as total from pg_locks;'
```

Reconfirm container/database names first. Aggregate connection states, application names, idle ages, and table maintenance statistics without printing SQL query text or row contents. An unnamed idle connection's owner remains a hypothesis until corroborated.

## Report and verify cleanup

Write a dated report under `/root/reports/`, separating measured facts, inferred causes, and proposed changes. Include the observation window, CPU normalization, memory accounting method, service ownership, current versus historical errors, expected gains, dependencies, and implementation risks.

Prioritize gains using evidence. In the teaching audit, five Python services loaded the same `potion-multilingual-128M` embedding model; mapping/source inspection and an isolated loading benchmark explained roughly 1.1 GB per copy. This is a diagnostic pattern, not a permanent baseline or proof that consolidation is already safe.

Treat first-token latency separately from total request duration. Resource observations can motivate a preflight/WorkingState investigation but do not establish its latency without timing evidence.

Before finishing, verify that audit samplers and benchmark helpers have exited. State explicitly that no production processes, timers, or configuration were changed. Give Monsieur findings and report links, not commands to execute.
