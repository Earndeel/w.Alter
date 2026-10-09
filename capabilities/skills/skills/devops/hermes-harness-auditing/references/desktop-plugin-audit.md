# Hermes Desktop plugin audit checklist

Use this reference when Monsieur asks which plugins are present in Hermes Desktop or asks for an explanation/security review of one.

## 1. Establish the source of truth

Record the surface before inspecting anything:

| Surface | Inventory/source | Typical location |
|---|---|---|
| Native Hermes Desktop runtime plugin | Settings → Plugins; local files | `$HERMES_HOME/desktop-plugins/<id>/plugin.js` |
| Bundled Desktop plugin | Desktop source/Vite glob | `apps/desktop/src/plugins/<id>/plugin.{ts,tsx}` |
| Python/gateway plugin | `hermes plugins list` | `$HERMES_HOME/plugins/` or repo `plugins/` |
| Web dashboard plugin | Dashboard SDK/manifest | dashboard-specific plugin directory |

`hermes plugins list` must not be presented as the Desktop UI plugin inventory. When Desktop is on a Mac and the Hermes backend is remote, inspect the Mac-local directory; the backend's plugin directory is a different surface.

If the Mac cannot be inspected, report the inventory as **UNKNOWN** and request either a Settings → Plugins screenshot or the relevant `plugin.js` files. Never convert absence of remote access into a claim that no Desktop plugins exist.

## 2. Per-plugin identity

Record only what is evidenced:

- folder name and plugin id;
- human name, if declared;
- source: bundled or runtime/user;
- enabled/disabled/error state from Settings → Plugins;
- `defaultEnabled`, if declared;
- file path and any declared backend manifest;
- whether the plugin is actually loaded or merely inventoried.

Do not invent version, author, permissions, or capabilities when the Desktop plugin contract does not declare them.

## 3. Trace the code paths

Inspect the default export and `register(ctx)`:

- `ctx.register`: status bar, panes, routes/pages, sidebar navigation, palette commands, or keybinds;
- `host.state.*`: live state observed by the plugin;
- `host.request`: gateway JSON-RPC methods and parameters;
- `host.onEvent`: event subscriptions and whether they are cleaned up;
- `host.notify`, `host.navigate`, `host.logs`, `host.status`, and `haptic` calls;
- `ctx.storage`: persisted values and whether they contain sensitive data;
- `ctx.rest` / `ctx.socket`: plugin-scoped backend paths and event streams;
- `ctx.i18n`: registered strings and any dynamic interpolation;
- cleanup/disposers and hot-reload behavior.

Use the app's SDK contract as the boundary. A disk plugin should only import `@hermes/plugin-sdk`, `react`, and `react/jsx-runtime`; flag undeclared imports or attempts to reach Electron/Node internals.

## 4. Security and side effects

Classify findings separately:

- **Low:** presentation-only UI, local labels, non-sensitive scoped storage;
- **Medium:** reads session/config/status data, subscribes to events, or calls gateway methods;
- **High:** writes configuration, triggers actions, sends messages, uploads data, opens external URLs, or uses a backend namespace;
- **Critical:** embedded credentials, unrestricted filesystem/process access, arbitrary remote code loading, or exfiltration of transcripts/tokens.

For each network or backend call, state the exact endpoint/method, data leaving the machine, trigger, and whether the user can disable the plugin. Never print tokens, cookies, or secret values during the audit.

## 5. Report format

```text
Plugin: <id/name>
Evidence: <Settings screenshot / exact path / source file>
Status: <enabled | disabled | error | unknown>
Purpose: <one sentence>
UI contributions: <panes/pages/status/palette/keybinds>
Backend/gateway access: <methods/endpoints or none>
Persistence: <keys/data or none>
External network: <host + payload class or none>
Risk: <low | medium | high | critical>
Verdict: <keep / disable / inspect further>, with reason
Unknowns: <what was not observable>
```

Keep **measured/observed** facts separate from **risk** and **unknown**. A plugin being listed is not proof that it is enabled; a plugin being enabled is not proof that its backend is reachable or that a contribution rendered successfully.
