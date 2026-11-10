---
name: walter-vm-architecture-audit
description: Use when auditing, documenting, reorganizing, or validating the current architecture of W.Alter and its Oracle Ubuntu ARM64 VM, including instance resolution, Walter modules, services, projects, applications, storage, runtimes, and compatibility paths.
---

# Walter VM architecture audit and controlled reorganization

## Establish the active instance and current Walter layout

Begin with read-only inspection. Never infer the active instance or module state from documentation alone.

```bash
cat /etc/walter/instance
walter instance show
ls -la /instances/monsieur
find /instances/monsieur -maxdepth 2 -not -path './state/*/*' -not -path '*/.git/*' | sort | head -120
walter layout
walter modules
walter status
```

Use `/etc/walter/instance` and `walter instance show` as the source for the active instance. Inspect `/instances/monsieur/config` and `/instances/monsieur/state` before changing instance configuration.

For machine-wide architecture, record these layers separately:

- `/walter`: Walter modules, code, memory, skills, and documentation.
- `/instances/monsieur`: instance-specific configuration and state.
- `/srv/projects/<client>/<project>`: first-party projects.
- `/srv/apps/<app>`: third-party or separately deployed applications.
- `/root/projects/<name>`: compatibility symlinks retained for configurations that still reference the old project paths.
- `/root/.hermes`: Hermes runtime, profiles, scripts, plugins, hooks, and schedules.
- `/root/archive`: reversible archives created during cleanup.
- `/etc/systemd/system` and `/root/.config/systemd`: service definitions.

## Inventory runtime services and dependencies

Collect the running services and Walter health separately. Do not treat a running process as proof that the corresponding Walter module is healthy.

```bash
walter status 2>/dev/null
walter check 2>/dev/null
systemctl --failed --no-legend
systemctl list-units --type=service --state=running --no-legend
systemctl --user list-units --type=service --state=running --no-legend
```

For each Walter module, record its identifier, kind, runtime health, services, requirements, missing paths, and forbidden imports. A useful JSON inspection is:

```bash
walter status 2>/dev/null | python3 -c '
import json,sys
d=json.load(sys.stdin)
for m in d["modules"]:
    print(m["id"], "|", m.get("kind"), "|", m.get("runtime_health"), "|", m.get("services"), "| req:", m.get("requires"))
'
```

Check the dedicated Walter services explicitly:

```bash
for u in edgewise-shop raw-vault-s3 walter-memory-gateway walter-llm walter-skills camoufox-max; do
  printf '%s ' "$u"
  systemctl is-active "$u"
done
walter standby status
```

Inspect service definitions before moving application directories:

```bash
grep -n -E 'ExecStart|WorkingDirectory|Environment' /etc/systemd/system/*.service
```

After every service path change, reload or restart only the affected unit and verify both systemd state and the application endpoint:

```bash
systemctl restart <service>
systemctl is-active <service>
journalctl -u <service> -n 20 --no-pager
curl -s -o /dev/null -w 'local %{http_code}\n' http://127.0.0.1:<port>/
curl -s -o /dev/null -w 'public %{http_code}\n' https://<hostname>/
```

For a systemd process, verify its actual working directory rather than trusting the unit file:

```bash
pid=$(systemctl show -p MainPID --value <service>)
readlink -f /proc/$pid/cwd
```

## Inventory the VM substrate

Record storage, memory, network, databases, containers, and runtimes as separate facts.

```bash
df -h /
free -g
ip -br a
wg show interfaces
tailscale status
psql -h 127.0.0.1 -p 5433 -U postgres -d hindsight -Atc "select n.nspname, count(c.*) filter (where c.relkind in ('r','p')), pg_size_pretty(coalesce(sum(pg_total_relation_size(c.oid)) filter (where c.relkind in ('r','p','m')),0)) from pg_namespace n left join pg_class c on c.relnamespace=n.oid where n.nspname !~ '^(pg_|information_schema)' group by 1 order by sum(pg_total_relation_size(c.oid)) desc;"
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'
which hermes codex claude dsh
ls /opt/dsh
ls /root/.hermes/profiles
ls /root/.hermes/plugins
```

Inspect application mounts and Compose metadata before relocating applications:

```bash
docker inspect <container> --format '{{.Name}} {{index .Config.Labels "com.docker.compose.project"}} {{index .Config.Labels "com.docker.compose.project.working_dir"}} {{range .Mounts}}{{.Type}}:{{.Source}} {{end}}'
```

## Reorganize projects and applications safely

Before moving anything, create a dated archive and capture Git state and service definitions.

```bash
archive=/root/archive/2026/rangement-lot3-$(date +%Y%m%d)
mkdir -p "$archive"
chmod 700 "$archive"
cp -a /etc/systemd/system/<affected-unit>.service "$archive"/
```

Use `/srv/projects/<client>/<project>` for projects and `/srv/apps/<app>` for deployed applications. Keep compatibility links under `/root/projects` when existing Hermes, systemd, or other configuration still references the old path:

```bash
mkdir -p /root/projects
ln -s /srv/projects/<client>/<project> /root/projects/<project>
```

After moving a project, search all configuration and runtime sources for stale paths:

```bash
grep -RIn '/root/projects\|/root/bin\|/root/work' \
  /etc/systemd /root/.config/systemd /usr/local/bin \
  /instances/monsieur/config /root/.hermes 2>/dev/null
```

Update documentation and local memory only after the path is verified in the live configuration. Record the change in `/walter/docs/DECISIONS.md` or the active Walter decision log, including the old path, new path, compatibility link, and validation performed.

## Store personal files in the Raw Vault with deduplication

Use the Walter memory object store for files that should be retained in the Raw Vault. The object store deduplicates by SHA-256, so inspect its semantics before bulk ingestion:

```bash
walter-memory objects --help
walter-memory objects put --help
grep -n -E 'def put|sha256|dedup|existing' /walter/memory/walter_memory/objects.py
```

Ingest one file first and verify the returned object identifier and storage key before processing a batch:

```bash
walter-memory objects put '<path>' --source vault --kind '<kind>' --privacy '<privacy>'
walter-memory objects search '<term>' --limit 20
```

For a batch, save every command result as JSONL with the source path, privacy classification, object ID, and storage key. Restrict permissions on temporary verification directories:

```bash
verify=/tmp/vault-verify-$(date +%s)
mkdir -p "$verify"
chmod 700 "$verify"
```

Verify that each stored object can be located and that duplicate source files resolve to the same object before removing local copies.

## Archive unused scripts and root clutter conservatively

Classify scripts using references from live systemd units, user services, profiles, plugins, hooks, schedules, Walter skills, and active configuration. Search by exact filenames or stems rather than assuming a script is dead because it is not a service.

```bash
cd /root/.hermes/scripts
ls -1 | grep -v __pycache__ > /tmp/hermes-script-names.txt
grep -rhoFw -f /tmp/hermes-script-names.txt \
  /etc/systemd/system /root/.config/systemd /usr/local/bin \
  /instances/monsieur/config /root/.hermes /walter/capabilities/skills 2>/dev/null \
  | sort -u > /tmp/hermes-live-references.txt
```

Move only files classified as unused into a dated archive. Preserve a manifest of live, skill-only, and archived scripts. Keep special runtime directories such as WebTop or computer-use tooling unless their dependencies have been checked separately.

## Final validation and reporting

Run the checks again after every reorganization batch:

```bash
systemctl --failed --no-legend
walter status
walter check
walter standby status
```

For public applications, test both loopback and public URLs. For tunnels, check the relevant peer and recent service logs:

```bash
tailscale status
journalctl -u <tunnel-service> -n 10 --no-pager
```

Report the resulting architecture with exact paths, active services, ports, dependencies, compatibility links, archive location, and unresolved items. Distinguish completed reversible moves from deletions awaiting approval.

## Pitfalls

- Do not assume `/walter` is the active instance; resolve `/etc/walter/instance` and `walter instance show` first.
- Do not rebuild Walter or introduce a second bus, registry, or memory system when the audit shows those components already exist.
- Do not remove `/root/projects` immediately after moving projects; existing Hermes and service configuration may still depend on those paths.
- Do not trust a successful `systemctl restart` alone; verify the process working directory and local/public HTTP behavior.
- Do not delete local files merely because they were placed in the Raw Vault. Confirm object IDs, storage keys, deduplication, and restoreability first.
- Do not delete a broken virtual environment or redundant copies solely because they appear unused. Archive them and request explicit approval before irreversible deletion.
- A failed orchestration or plan-hook call can time out without executing. Verify state with shell commands before retrying or claiming that the operation ran.
- Keep personal files and archives permission-restricted, and never put credentials, tokens, or keys into reports or decision logs.
