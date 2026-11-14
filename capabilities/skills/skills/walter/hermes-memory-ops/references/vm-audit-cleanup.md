# VM Audit & Cleanup Patterns

## Disk Space Quick Wins (measured 2026-06-07, Oracle ARM 145GB)

| Target | Typical Size | Safe to Delete | Command |
|---|---|---|---|
| ~/.hermes/heapdumps/ | 5-6 GB | Yes (old Node.js heap snapshots) | `rm -f ~/.hermes/heapdumps/*` |
| ~/.cache/uv | 10-25 GB | Yes (rebuilt on demand) | `uv cache clean` |
| ~/.cache/pip | 1-2 GB | Yes | `pip cache purge` |
| Docker exited containers + dangling images | 5-15 GB | Yes | `docker container prune -f && docker image prune -a -f && docker volume prune -f` |
| ~/.hermes/logs/memory-autopilot/ (>7d) | 1-2 GB | Keep 7 days | `find path -mtime +7 -delete` |
| ~/.hermes/logs/hindsight-api.log | 100+ MB | Truncate (service running) | `: > path` |
| /var/log/journal | 400+ MB | Compact to 200M | `journalctl --vacuum-size=200M` |
| ~/.npm | 2+ GB | Partial | `npm cache clean --force` |
| ~/.hermes/state-snapshots/ | ~1 GB | After validating update | `rm -rf` once confirmed |
| LanceDB legacy (lancedb-gemini) | 200 MB | If Qdrant replaces it | `rm -rf` |

## Docker: FreeSWITCH Build Artifacts

Multiple failed FreeSWITCH ARM builds leave behind exited containers and untagged intermediate images. These can accumulate 10+ GB. Safe to prune — the Dockerfile can rebuild if needed.

## Services to Investigate

- `neo4j` (624 MB, `inactive`) — installed but not used. Candidate for removal.
- `ModemManager`, `wpa_supplicant`, `rpcbind` — unlikely needed on a cloud VM. Low priority.
- `hermes-agent.service` / `hermes-gateway.service` — masked and failed. Legacy reliquats from before the TUI-based startup. Not a problem (gateway runs via `hermes_cli.main gateway run`).

## TUI Ghost Sessions

Long-running SSH sessions that disconnect leave TUI processes alive (python tui_gateway + node entry.js + pyright LSP). Each consumes 200-400 MB RAM. They accumulate over days.

Detection: `pgrep -af "tui_gateway.entry"` — check TTY and age.
User preference: NEVER kill without asking. Just report them.
