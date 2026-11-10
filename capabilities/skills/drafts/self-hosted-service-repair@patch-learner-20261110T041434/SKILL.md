---
name: self-hosted-service-repair
description: Use when repairing self-hosted services across remote hosts.
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [self-hosted, remote-access, docker, backup, recovery, operations]
---

# Self-Hosted Service Repair

Use this skill for a self-hosted application whose client is failing, whose backend needs an upgrade, or whose remote host must be recovered before the application can be changed. The workflow applies to password managers, media services, dashboards, gateways, and other Docker- or systemd-hosted services.

## Core model: three separate layers

Always distinguish:

1. **Client layer** — desktop/mobile/browser version, cache, decryption, sync behavior.
2. **Application layer** — server implementation, web vault/API version, containers, volumes, compose files.
3. **Infrastructure layer** — VM/cloud project, DNS, firewall, SSH/serial access, disks and snapshots.

A client compatibility error is not proof that application data is lost. Conversely, a healthy public endpoint is not proof that an agent has administrative access to the host.

## Required sequence

### 1. Define the repair gate

Before changing anything, state the exact success condition:

- the public endpoint remains reachable;
- the server version is compatible with the installed clients;
- existing data volumes are preserved;
- the client can authenticate, sync, decrypt, and display existing records.

Do not call the work repaired until the final client-level check passes.

### 2. Prove target identity

Resolve and record the service hostname, then compare it with the configured server URL and the infrastructure control plane:

- DNS target/IP;
- HTTP(S) response and application identity/version endpoint;
- cloud project, VM name, zone/region, and external IP;
- host tags or firewall route when relevant.

Never update the first host that happens to answer on a familiar port. A working web endpoint and a reachable VM are two different facts.

### 3. Establish an administrative path before touching the service

Use the least invasive already-authorized path:

1. existing SSH alias/key or documented tunnel;
2. authenticated cloud console / Cloud Shell;
3. provider-native serial or recovery console;
4. only then, a planned recovery procedure with an explicit backup and rollback gate.

For Google Cloud, Cloud Shell can be used for read-only discovery:

```bash
gcloud compute instances describe INSTANCE \
  --zone=ZONE --project=PROJECT --format=json
```

When displaying metadata, print only keys, usernames, status, tags, and resource names. Never print private keys, passwords, tokens, or complete secret-bearing metadata values.

**Important access invariant:** a public SSH key appearing in project or instance metadata does not prove that the guest OS has accepted it. If `gcloud compute ssh` still returns `Permission denied (publickey)`, stop retrying blindly. Do not declare the VM accessible, do not change the service, and do not reboot it merely to make the failed path look busy. Obtain a known-good admin account/key or use a separately verified recovery path.

### 4. Create a rollback point before host modifications

Use both layers when available:

- application-level encrypted export, protected with the vault/master password and mode `0600`;
- hypervisor disk snapshot before changing host files, metadata, startup scripts, or containers.

Keep the previous image/tag and compose configuration. Do not use `docker system prune`, delete volumes, or overwrite an existing backup as part of a routine upgrade.

### 5. Inspect the deployment read-only

Once host access is proven, identify the real deployment rather than assuming a path:

```bash
id -un
hostname
find /opt /srv /home -maxdepth 3 -iname '*compose*.y*ml' -o -iname 'docker-compose.y*ml' 2>/dev/null
docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}'
docker volume ls
```

Read the compose file and environment references without printing secret values. Record container names, image tags/digests, bind mounts, named volumes, ports, and health status. Verify that the data volume is the one used by the running container.

For scheduled host scripts with database connection failures, compare the script's effective endpoint with `docker inspect CONTAINER` → `NetworkSettings.Ports` and `Networks`. Prefer an existing published loopback endpoint for host clients; use service DNS for clients on the container network. Do not replace one ephemeral container IP with another. Preserve explicit connection overrides and credentials, then exercise the script's actual SELECT queries in a read-only transaction with connection and statement timeouts; report counts, never retrieved records. A successful SELECT proves the connection path, not completion of the scheduled extraction job.

For an unhealthy container whose application still responds, execute the exact configured healthcheck and inspect status plus redirect destination before restarting anything. If HTTPS enforcement redirects a loopback HTTP probe, verify the proxy-trust configuration and test the appropriate forwarded-protocol header on that local probe. Require the expected status and health body with a bounded timeout; do not accept redirects as healthy or disable HTTPS/authentication. A probe-only repair must preserve the current image, volumes and application settings.

### 6. Apply the smallest compatible update

Separate configuration repair from version upgrade. For endpoint or healthcheck repairs, retain the running image digest and change only the proven faulty setting; avoid silently upgrading a mutable image tag. Stage the change, reproduce the failure and passing probe, and confirm any required interruption before recreating the affected service. Editing a compose file does not change an existing container's healthcheck: verify the activated container configuration and subsequent health result separately.

When a version upgrade is actually required, prefer the vendor's documented path and a pinned compatible release. Pull the selected image, recreate only the relevant service, and preserve volumes:

```bash
docker compose pull SERVICE
docker compose up -d SERVICE
docker compose ps
```

Do not combine an application upgrade with unrelated OS, Docker, firewall, DNS, or credential changes. If the service uses a reverse proxy, validate the proxy and the application separately.

### 7. Verify from outside and from a client

Check all of the following:

- external HTTPS endpoint and TLS;
- application config/version endpoint;
- container health and recent logs, with secrets redacted;
- login and sync from the affected client;
- decryption/display of existing records;
- record count or metadata comparison against the pre-change state.

Keep the encrypted export and rollback image until every affected client is healthy.

## Remote-console control gate

When Cloud Shell is being driven through a remote Mac or another graphical bridge, prove the control channel before issuing snapshots, metadata changes, startup scripts, resets, or container commands:

1. Check the bridge health endpoint.
2. Capture a screenshot and verify that it is a real, readable screen rather than an all-black image. A 2880x1800 PNG around 100 KB is a strong sign that Screen Recording/TCC or the lock screen is blocking capture.
3. Send one harmless read-only command and verify its visible output. An endpoint returning `ok` or `typed` is not proof that the terminal received or executed the command.
4. If a combo endpoint reports an `osascript`/`System Events` Accessibility error, stop GUI automation. Do not keep typing, do not paste long encoded payloads, and do not reset or modify the VM blindly.
5. Ask the user to foreground/unlock the console and grant the required macOS Screen Recording/Accessibility permission, or have the user run one read-only `gcloud compute instances list/describe` command manually and return the output. Resume only after the target project, zone, status, and current metadata are visible.

Never encode a long recovery script into simulated keystrokes unless paste context has been verified. Use short, observable commands; the recovery path is not considered exercised until its terminal output and a real SSH probe are both verified.

## Recovery and stop conditions

Stop and report a blocker when:

- the target VM cannot be tied unambiguously to the public service;
- no authorized administrative path works;
- a backup cannot be verified;
- the deployment layout or data volume is unknown;
- an upgrade would require deleting or migrating data without a tested rollback;
- a client-side compatibility hypothesis has not been confirmed against the actual server version.

A recovery console, startup script, disk attachment, or VM restart is a separate high-impact operation. Use one only after the snapshot/backup gate and only with a verified, reversible plan; do not present an untested recovery attempt as a standard fix.

## Secret-handling rules

- Never place passwords, private keys, API tokens, or vault exports in screenshots, chat output, git, or shell history.
- Use temporary files with `umask 077`; remove them after use.
- Prefer metadata-only queries when searching a credential vault.
- Remove temporary cloud SSH metadata/keys after the maintenance session if they were added solely for access.
- Report operational identifiers and versions, not secret material.

## Supporting reference

See `references/gcp-cloud-shell-preflight.md` for the validated Cloud Shell discovery pattern and the SSH-access stop condition.

For scheduled or autonomous jobs that call an external model or mutate durable state, load `references/autonomous-job-verification.md` before execution; it defines the real-completion gates beyond process exit status.

For scheduled ingestion repairs, load `references/scheduled-pipeline-cursors.md` to verify cursor ordering, durable retries, exit status, and disclosure preservation before reactivation.

## Common pitfalls

- Treating **Bitwarden** (the client/product) and **Vaultwarden** (the self-hosted compatible server) as the same layer.
- Assuming a successful `bw sync` or public API response means the host can be administered.
- Updating the client first when the compatible server release is the actual fix.
- Adding a cloud SSH key and assuming guest-agent propagation succeeded.
- Starting recovery actions before making an encrypted application export and infrastructure snapshot.
- Calling a task complete after writing commands but before exercising the service and a real client sync.

## Recover disk space on the W.Alter VM

1. Clarify whether « mémoire saturée » means RAM/swap or disk storage before restarting services. Measure disk usage with `df -h -x tmpfs -x overlay -x squashfs`, then `du -xh --max-depth=1 / 2>/dev/null | sort -rh | head -20`. Use `-x` to stay on the filesystem being investigated.
2. Narrow the largest directories with `du -xh --max-depth=2 /root /var /user /usr /tmp 2>/dev/null | sort -rh | head -45`. Inspect Docker with `docker system df`, `docker ps -a --format '{{.Image}} {{.Names}} {{.Status}}'`, and journal size with `journalctl --disk-usage`.
3. Check ownership and live references before removing caches, browser versions, downloaded models or temporary checkouts. Inspect Git status and worktree registrations for temporary repositories. A directory's age or a Docker volume's dangling status alone does not prove its contents are disposable. Do not remove frozen engine dependency caches such as `/services/dsh/npm-cache`.
4. For candidate Docker volumes, run `docker volume inspect VOLUME` and inspect contents through a read-only mount: `docker run --rm -v VOLUME:/v:ro alpine ls -la /v`. Archive valuable contents before targeted removal. Avoid blanket volume pruning. Put change records and backups under the instance's `backups/changes/` directory, resolving the instance through `walter instance`.
5. Inspect PostgreSQL backup retention before deleting dumps: `readlink -f /usr/local/sbin/walter-pg-backup`. The script is currently `/walter/ops/backup/scripts/walter-pg-backup`. A Sunday weekly dump can duplicate that day's completed daily dump. On the same filesystem, create the weekly name using `ln` instead of `cp`; both names then retain the same immutable bytes, and deleting the daily name leaves the weekly backup intact. Back up the script before editing, preserve daily/weekly retention, and verify linked files using `stat -c '%d %i %h %n' DAILY WEEKLY`. Never modify a dump in place after linking it. Do not shorten retention without authorization or treat two hard links as independent backup copies.
6. Verify actual recovery with `df -h /`, inspect `docker ps`, and check affected systemd services. Hermes gateway is a user unit: `systemctl --user is-active hermes-gateway`. Record reclaimed space, removed categories, retained archives and any remaining cleanup that needs authorization.
