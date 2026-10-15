---
name: walter-soul-maintenance
description: Use when changing W.Alter’s shared identity, communication rules, or generated personality profiles across Hermes, Claude Code, Codex, MCP and voice.
---

## Inspect the source and scope

Read `/opt/walter-soul/identity.md`, `rules.md` and `runtimes/*.md`. Shared identity belongs in `identity.md`; shared operating rules belong in `rules.md`; channel or runtime constraints belong in the appropriate runtime supplement.

Inspect the relevant generated profile before claiming which personality a session receives. Claude Code’s W.Alter profile is `/opt/walter-profiles/claude-code/CLAUDE.md`; sessions opened in `/root` use the technician instructions. Do not assume every session loads the W.Alter profile.

## Back up and edit the canonical files

```bash
tar czf /root/.hermes/backups/walter-soul-$(date -u +%Y%m%dT%H%M%SZ).tgz -C /opt walter-soul
git -C /opt/walter-soul status --short
```

Edit the canonical source files, preserving unrelated changes. Never edit generated `SOUL.md` or generated runtime profiles directly: regeneration can overwrite those edits, and `check` detects drift.

For a length rule, inspect every occurrence before changing it:

```bash
rg -n '1 à 3|1-3|phrases|Telegram' /opt/walter-soul/identity.md /opt/walter-soul/rules.md /opt/walter-soul/runtimes /opt/openclaw/hermes_voice_bridge.py
```

Keep Telegram brevity in `runtimes/hermes.md`, explicitly scoped to Telegram. Remove obsolete exceptions in `runtimes/agent-cli.md` when removing the corresponding shared restriction. Voice can contain an independent length rule in `/opt/openclaw/hermes_voice_bridge.py`; inspect it separately.

## Regenerate and verify

```bash
git -C /opt/walter-soul diff --check
git -C /opt/walter-soul diff
/opt/walter-soul/bin/walter-soul sync
/opt/walter-soul/bin/walter-soul check
```

Require all five generated outputs to pass the check. Inspect the affected generated profiles to confirm both the requested change and its channel scope. Generation alone does not prove an already running session has reloaded its instructions.

If modifying the voice bridge itself, compile it before restarting:

```bash
/usr/bin/python3 -m py_compile /opt/openclaw/hermes_voice_bridge.py
```

Restart `hermes-bridge` only after verifying no call is active, then check service health and reconnection:

```bash
systemctl restart hermes-bridge
systemctl is-active hermes-bridge
journalctl -u hermes-bridge --since '-1 minute' --no-pager
```

Verify the journal reports connection to Asterisk ARI. Report which profiles changed and which running consumers were verified.
