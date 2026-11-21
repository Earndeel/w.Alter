---
name: dsh-web-ui-composition
description: Use when customizing W.Alter’s DSH web interface, removing interface controls, or preserving UI changes through harness regeneration.
---

## Locate the running interface and its composition

Read the relevant Walter procedure before infra changes. Inspect live state rather than assuming the installed package or generated profile is authoritative:

```bash
systemctl cat dsh-web.service
cat /opt/dsh/package.json
cat /opt/dsh/home/profiles/web/package.json
cat /opt/dsh/home/profiles/web/cordis.yml
cat /opt/dsh/home/profiles/web/cordis.patch.yml
```

The observed installation uses `/opt/dsh/node_modules/.bin/dsh`, `DSH_HOME=/opt/dsh/home`, and profile `web`. The production service listens on loopback; Tailscale exposes port 3080. Preserve that access arrangement.

`cordis.yml` is an empty root composed from bundles and patches. Customize through the composition and patch mechanisms, not by editing that root or installed package bundles.

## Separate generated settings from instance settings

Inspect the `# walter:dsh-web` managed fence before changing the web profile. Find the generator through the module interface:

```bash
walter path core
```

Within that returned directory, locate the implementation:

```bash
rg -n 'DSH_WEB_OFF|_dsh_web_profile|walter:dsh-web' .
```

Shared UI disables belong in the Walter core composition. Instance-specific display name and greeting belong in instance configuration. Do not add permanent duplicates outside the managed fence: regeneration can overwrite managed edits, and duplicate rows obscure ownership.

The session’s final integration placed shared disables in `DSH_WEB_OFF` in the core composition, commit `5880a06`. The generated profile retained the connection row and the instance-specific `walter-ui` insertion outside the fence. Verify current ownership before changing it.

## Inspect plugin dependencies before removing controls

Use installed READMEs, package manifests, and client registrations to identify the plugin responsible for a control:

```bash
cd /opt/dsh/node_modules/@deepseek-ai
rg -n 'ui-model-selection|ui-agent-preset|ui-plugin-manager' --glob package.json
rg -n 'register|panellist|conversation.composer' dsh-client-ui-sidebar/lib/client.js dsh-client-ui-model-selection/lib/client.js
```

Inspect whether matches represent runtime requirements or development dependencies. Disable the responsible plugin in the composition rather than merely hiding its DOM with CSS. Check related settings pages and required services before disabling anything.

The verified lean interface disabled these ten plugin IDs:

- `ui-brand-official`
- `ui-model-selection`
- `ui-agent-preset`
- `ui-plugin-manager`
- `ui-settings-plugin-inventory`
- `ui-settings-plugins`
- `ui-settings-shell`
- `ui-settings-agent-loop`
- `ui-settings-subagent`
- `ui-settings-web-search`

Treat this list as an observed working preset, not a requirement for every customization.

For large minified bundles, use narrow `rg` searches or a small Python parser. Complex contextual regular expressions hit the installed grep implementation’s complexity limit during this session.

## Validate in isolation, then verify production

Back up affected files under the instance’s `backups/changes` directory before modifying them. Use a per-session scratch directory and a copied DSH home for staging. Inspect copied patches for absolute references to the production home before launching the copy.

Run staging through a systemd unit, with its own `DSH_HOME`, loopback address, and unused port; this session used unit `walter-ui-dev` on port 3091. Stop staging before applying the reviewed composition to production.

After applying through the current harness procedure:

```bash
systemctl restart dsh-web
systemctl is-active dsh-web
journalctl -u dsh-web --since '-2 minutes' --no-pager
```

Verify the real tailnet endpoint on port 3080 in an authenticated browser. Check the home view, an existing conversation, settings, and the composer. Confirm requested controls disappeared, the French W.Alter branding remains, and typing enables the send button. Clear test text afterward; testing button activation does not require sending a message.

Repeat browser verification after harness regeneration. A successful service restart alone does not establish that generated configuration preserved the UI changes. Coordinate ownership when another session is editing the same profile or composition.
