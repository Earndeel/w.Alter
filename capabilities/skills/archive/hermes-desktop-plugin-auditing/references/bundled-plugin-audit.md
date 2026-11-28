# Bundled plugin audit reference

This reference records the extraction pattern and evidence from one packaged
Hermes Desktop audit. Re-run the inventory for each installed build; bundled
plugin names are release data, not a permanent contract.

## macOS extraction recipe

1. Locate the installed bundle with Spotlight metadata or the known
   `/Applications/Hermes V2.app` path.
2. Copy `Contents/Resources/app.asar` and the adjacent
   `Contents/Resources/app.asar.unpacked/` to a temporary analysis directory.
   Keep the unpacked directory adjacent to the copied archive; ASAR tooling
   resolves it by the exact `<archive>.unpacked` name.
3. List or extract with an ASAR-aware reader:

   ```bash
   npm exec --yes --package=@electron/asar@3.4.1 -- \
     asar list /tmp/hermes-v2-mac.asar
   npm exec --yes --package=@electron/asar@3.4.1 -- \
     asar extract /tmp/hermes-v2-mac.asar /tmp/hermes-v2-extract
   ```

4. Search extracted renderer assets for `../plugins/`, `kind:\`bundled\``,
   `defaultEnabled`, and plugin IDs. In minified bundles, a small Python
   substring/context probe is more reliable than reading an entire one-line
   asset into the model.
5. Read only the plugin decision key from Chromium local storage. Current
   builds use `hermes.desktop.pluginDecisions.v2`; LevelDB files can be scanned
   for that exact key and a narrow surrounding value without dumping the app
   profile.

## Registry pattern observed in Hermes V2

The compiled renderer contained a static registry equivalent to:

```text
Jfe = Object.assign({
  "../plugins/example/plugin.tsx": ExamplePlugin,
  "../plugins/gateway-pill/plugin.tsx": GatewayPillPlugin,
  "../plugins/kanban/plugin.tsx": KanbanPlugin,
})
```

The registry then emitted records with `kind: "bundled"`, applied
`defaultEnabled ?? true`, and overrode that default from
`hermes.desktop.pluginDecisions.v2`.

The observed plugin definitions were:

- `example` / **Example Plugin** — demonstration status-bar click counter,
  gateway-event counter, namespaced storage, and reset commands.
- `gateway-pill` / **Gateway Pill** — gateway connection/readiness status pill,
  recent logs, messaging-platform status, and gateway/system actions.
- `kanban` / **Kanban** — `/kanban` page, sidebar navigation, task count pill,
  open/new-task commands, and Kanban API/event integration; it declared
  `defaultEnabled: false` in this build.

In the audited installation the persisted decision was:

```json
{"kanban": true}
```

The external `~/.hermes/desktop-plugins/` directory had no child plugin
folders. This means the correct report was three bundled plugins, with Kanban
explicitly enabled, and zero external disk plugins.

## Reporting template

```text
Bundled: <id> — <name> — default <on/off>
Disk/runtime: <profile path>/<name>/plugin.js — present/missing
Active: <id> — enabled by default / explicit decision / disabled
```

Always state the source bucket. “No plugins” is ambiguous and should be
replaced with “no external disk plugins; bundled plugins found/not found”.
