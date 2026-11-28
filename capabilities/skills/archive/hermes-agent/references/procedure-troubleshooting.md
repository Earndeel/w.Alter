### Troubleshooting

### Voice not working
1. Check `stt.enabled: true` in config.yaml
2. Verify provider: `pip install faster-whisper` or set API key
3. Restart gateway: `/restart`

### Tool not available
1. `hermes tools` — check if toolset is enabled for your platform
2. Some tools need env vars (check `.env`)
3. `/reset` after enabling tools

### Model/provider issues
1. `hermes doctor` — check config and dependencies
2. `hermes auth add <provider> --type oauth` — re-authenticate OAuth providers
3. `hermes auth list <provider>` — verify credentials are present and healthy
4. Check `.env` has the right API key

### Changes not taking effect
- **Tools/skills:** `/reset` starts a new session with updated toolset
- **Config changes:** `/restart` reloads gateway config
- **Code changes:** Restart the CLI or gateway process

### Updating Hermes with local modifications
If you run `hermes update` while the git checkout at `~/.hermes/hermes-agent` has uncommitted changes, the update will fail or overwrite your work. Always audit first:

```bash
cd ~/.hermes/hermes-agent
git status --short          # see modified + untracked files
git diff --stat             # scope of changes
```

If you have modifications you want to keep:

```bash
git stash push -m "description"
hermes update
git stash pop               # rebase your changes onto latest main
```

If `stash pop` produces conflicts, resolve them manually before restarting Hermes. Untracked files (e.g., new plugins, scripts) survive `hermes update` untouched, but verify they don't conflict with newly-added upstream files.

Common local modifications to preserve:
- `agent/context_compressor.py` — smart threshold strategies
- `gateway/run.py` — gateway hygiene hooks
- `tools/*.py` — provider-specific robustness patches
- `plugins/` — custom memory backends or integrations

### Gateway issues
1. `hermes skills list` — verify installed
2. `hermes skills config` — check platform enablement
3. Load explicitly: `/skill name` or `hermes -s name`

### Gateway issues
Check logs first:
```bash
grep -i "failed to send\|error" ~/.hermes/logs/gateway.log | tail -20
```

### Gateway watchdog crash loop (systemd)

A `hermes-watchdog.sh` wrapper that loops `hermes gateway run --replace` will crash-loop silently if:
1. Hermes overwrites `gateway.pid` with JSON (`{"pid": N, "kind": "hermes-gateway", ...}`) instead of a bare PID
2. The watchdog reads JSON, `kill -0` fails, it thinks the process is dead, spawns another
3. The new gateway fails with "Telegram bot token already in use" (exit 0 = conflict, not error)
4. `Restart=on-failure` doesn't fire because exit code is 0

**Symptom**: gateway restarting every 10-20 seconds in journalctl, Telegram disconnects every few minutes.

**Fix**: Replace the watchdog wrapper with a direct systemd service:
```ini
# /etc/systemd/system/hermes-agent.service
[Service]
Type=simple
ExecStart=/root/.local/bin/hermes gateway run
Restart=always
RestartSec=15
```
Key: `Restart=always` (not `on-failure`), no `--replace` flag (let systemd own the lifecycle), no watchdog wrapper. The `--replace` flag causes the gateway to exit 0 on conflict, which `Restart=on-failure` ignores.

### Background task notifications not arriving over SSH

When connecting to a remote Hermes instance via SSH, background task notifications (`notify_on_complete`) are delivered to the terminal PTY where the TUI runs. If the SSH connection drops, the PTY dies and notifications are lost — even if you're using a client-side SSH multiplexer like `cmux` (macOS) or SSH `ControlMaster`, which preserve TCP but not terminal state.

**Fix:** Run tmux on the **server side** so Hermes TUI survives SSH disconnects. Full recipe in `references/ssh-tmux-persistence.md` — includes the `.bashrc` auto-attach snippet, daily workflow, and pitfalls (`.bashrc` write protection, server reboot recovery).

For macOS **cmux** push notifications specifically (not just session persistence), see `references/cmux-notify-tui.md` — covers the OSC 777 escape-sequence path, the `allow-passthrough` pitfall, and the frontend/backend event wiring.

Quick check:
```bash
# See if Hermes is running on bare SSH PTYs (fragile) or inside tmux (safe)
ps -eo pid,tty,cmd | grep hermes | grep -v grep
# pts/* = bare SSH PTY → at risk
# tmux   = inside tmux → safe
```

---

## Where to Find Things

| Looking for... | Location |
|----------------|----------|
| Config options | `hermes config edit` or [Configuration docs](https://hermes-agent.nousresearch.com/docs/user-guide/configuration) |
| Available tools | `hermes tools list` or [Tools reference](https://hermes-agent.nousresearch.com/docs/reference/tools-reference) |
| Slash commands | `/help` in session or [Slash commands reference](https://hermes-agent.nousresearch.com/docs/reference/slash-commands) |
| Skills catalog | `hermes skills browse` or [Skills catalog](https://hermes-agent.nousresearch.com/docs/reference/skills-catalog) |
| Provider setup | `hermes model` or [Providers guide](https://hermes-agent.nousresearch.com/docs/integrations/providers) |
| Kie.ai repro notes | `references/kie-ai-hermes-cli-repro.md` |
| Platform setup | `hermes gateway setup` or [Messaging docs](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/) |
| MCP servers | `hermes mcp list` or [MCP guide](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp) |
| xAI auth (SuperGrok/API key) | `references/xai-auth-flow.md` |
| Profiles | `hermes profile list` or [Profiles docs](https://hermes-agent.nousresearch.com/docs/user-guide/profiles) |
| Cron jobs | `hermes cron list` or [Cron docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron) |
| Memory | `hermes memory status` or [Memory docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory) |
| Env variables | `hermes config env-path` or [Env vars reference](https://hermes-agent.nousresearch.com/docs/reference/environment-variables) |
| CLI commands | `hermes --help` or [CLI reference](https://hermes-agent.nousresearch.com/docs/reference/cli-commands) |
| Gateway logs | `~/.hermes/logs/gateway.log` |
| Session files | `~/.hermes/sessions/` or `hermes sessions browse` |
| Source code | `~/.hermes/hermes-agent/` |

---

