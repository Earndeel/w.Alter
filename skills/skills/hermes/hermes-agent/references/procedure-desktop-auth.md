## Hermes Desktop App (macOS GUI)

Native macOS app for managing Hermes workspaces. Connects via SSH alias to the VPS.

### SSH Config Requirements

The app reads `~/.ssh/config` for connection profiles. Critical:
- **IdentityFile must use absolute path** — `~` expansion fails in GUI context. Use `/Users/<user>/path/to/key` not `~/path/to/key`.
- **Remove `LocalForward` lines** if ports are already in use — SSH exits 255 on bind failure, app treats as connection failure.
- **Test**: `ssh -o BatchMode=yes <alias> "echo ok"` must return exit 0.

### File Permissions (VPS side)

App connects as the SSH user (e.g., `ubuntu`), not root. If Hermes home is `/root/.hermes/`, the SSH user needs traverse+read permissions.

**Symlink**: `ln -sf /root/.hermes /home/ubuntu/.hermes`

**Permission fix**:
```bash
chmod 711 /root /root/.hermes
chmod -R g+rX /root/.hermes/skills /root/.hermes/memories /root/.hermes/sessions /root/.hermes/profiles /root/.hermes/agents /root/.hermes/workspace
chmod g+x /root/.hermes/skills /root/.hermes/memories /root/.hermes/sessions /root/.hermes/profiles /root/.hermes/agents /root/.hermes/workspace
usermod -a -G root ubuntu
```

**⚠️ NEVER use `mount --bind` + `remount,ro`** — this remounts the SOURCE as read-only too, breaking the live system.

### TUI Session Orchestrator (Ctrl+X)

The Ink-based TUI (`hermes --tui`) has a session orchestrator panel (`ActiveSessionSwitcher` component) that opens with **Ctrl+X**. It lists all live sessions with their status (idle/starting/waiting/working) and model, and lets you:
- ↑↓ navigate between sessions
- Enter: switch to session / start new one
- Ctrl+N: create new live session
- Ctrl+D: close session
- Tab: change model before starting
- Ctrl+R: refresh list
- Esc: close panel

Accessible via `/sessions` slash command or the Ctrl+X hotkey. Not visible by default — must be invoked.

---

### Sections
Connections, Overview, Sessions, Workflows, Cron Jobs, Kanban, Files, Usage, Skills, Terminal

---

**Pitfalls**
- `hermes auth add` with `--type oauth` may hang on headless VMs with no browser or blocked egress to `chatgpt.com`. Use the manual device code workaround documented in `references/openai-codex-oauth-device-flow.md`.
- If the VM's IP is blocked by the OAuth provider (403 responses), run the device code flow from your local machine and copy the resulting tokens into the VM's profile `auth.json`.
- Never place a second credential directly in `~/.hermes/auth.json` when you meant `~/.hermes/profiles/<name>/auth.json`. Verify with `hermes auth list` after adding.

### Credential Pools

```
hermes auth add             Interactive credential wizard
hermes auth list [PROVIDER] List pooled credentials
hermes auth remove P INDEX  Remove by provider + index
hermes auth reset PROVIDER  Clear exhaustion status
```

### Multi-Account OAuth for the Same Provider (e.g., two OpenAI Codex accounts)

Use **profiles** to keep multiple OAuth accounts fully isolated without overwriting each other:

```bash
# Create a new profile cloned from the default
hermes profile create openai2 --clone

# Switch to it and add the second OAuth credential
hermes profile use openai2
hermes auth add openai-codex --type oauth

# Switch back to the main profile anytime
hermes profile use default
```

**Why profiles instead of credential pools on the same profile?**
- The `hermes auth add` command **appends** to the pool (it does not overwrite), but OAuth device-code flows can block on some networks (IP-level 403 from `chatgpt.com` on certain cloud providers).
- Profiles give **complete isolation**: separate `auth.json`, `config.yaml`, `.env`, sessions, skills, and memory.
- You can run both simultaneously: `hermes chat` (default profile) and `openai2 chat` (second profile).

**If the device-code flow is blocked (403 from the provider):**
- Run the OAuth flow from your **local machine** (not the cloud VM), then inject the resulting `access_token` + `refresh_token` into the target profile's `auth.json`.
- Alternatively, serve a local HTML page that performs the device-code flow in the browser via JS fetch, then copies the JSON output. See `references/openai-codex-device-flow.md`.

### Credential Pools

```
hermes insights [--days N]  Usage analytics
hermes update               Update to latest version
hermes pairing list/approve/revoke  DM authorization
hermes plugins list/install/remove  Plugin management
hermes honcho setup/status  Honcho memory integration
hermes memory setup/status/off  Memory provider config
hermes completion bash|zsh  Shell completions
hermes acp                  ACP server (IDE integration)
hermes claw migrate         Migrate from OpenClaw
hermes uninstall            Uninstall Hermes
```

---

