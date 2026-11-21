# Prouver qu'un tool/plugin est réellement enregistré et appelé

Verified 2026-08-11 while proving walter_browse registration in the real
Hermes harness.

## 1. L'activateur réel : le champ plugins.enabled dans la config

User plugins are **opt-in**. Without an entry the plugin is skipped at boot
with `not enabled in config (run hermes plugins enable ...)`. Read the
`plugins:` section of the active Hermes config to confirm the tool is
allowed.

## 2. La commande hermes plugins list ne montre PAS les plugins user

The CLI listing shows **bundled** plugins only. Grepping it for a user
plugin (e.g. walter-browse) returns nothing even when the plugin is loaded
and working. Do NOT conclude "not registered" from that listing — it is a
known misdirection.

## 3. Preuve runtime authentique : PluginManager._plugin_tool_names

Load the real plugin manager from the Hermes repo and read the registry:

```python
import os, sys, logging
from hermes_cli.plugins import PluginManager
logging.disable(logging.DEBUG)
mgr = PluginManager()
mgr.discover_and_load(force=True)
assert "walter_browse" in mgr._plugin_tool_names
for key, p in mgr._plugins.items():
    if p.manifest and p.manifest.name == "walter-browse":
        print(p.manifest.name, "enabled=", p.enabled, "error=", p.error)
```

## 4. Piège : get_hermes_home() peut pointer vers un sous-profil

`get_hermes_home()` can resolve to a Google-accounts sub-profile
(e.g. under /root/.hermes/google-accounts/...) instead of the real install
root. There, plugins.enabled reads None and the user plugin is not
discovered. Always force HERMES_HOME to the real install root (the path
where ~/.hermes/plugins/ holds the user plugin) in runtime proofs. The CLI
uses the configured profile too.

## 5. Dossier de plugin avec tiret → import par chemin

Plugin dir names like walter-browse contain dashes, so a plain import fails.
Load by path with importlib:

```python
import importlib.util
spec = importlib.util.spec_from_file_location(
    "walter_browse_plugin", "/root/.hermes/plugins/walter-browse/__init__.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
```

## 6. Instrumenter le vrai harness (tool calls réels)

Run prompts via `hermes chat -q "<prompt>" --source wb-frontdoor`, then read
the Hermes session DB (`/root/.hermes/state.db`): messages.tool_calls holds
**double-escaped** JSON; the arguments field is sometimes a dict, sometimes
a string, sometimes null — filter NULL rows and unescape repeatedly:

```python
import sqlite3, json
con = sqlite3.connect("/root/.hermes/state.db")
cur = con.cursor()
cur.execute("SELECT id FROM sessions WHERE source='wb-frontdoor' ORDER BY started_at")
sids = [r[0] for r in cur.fetchall()]
def unescape(s):
    z = s
    for _ in range(3):
        try: z = json.loads(z)
        except Exception: break
    return z
```

Parsing pitfalls:
- deferred plugin tools arrive via a `tool_call` whose arguments nest
  `{"name": ..., "arguments": {...}}`;
- `tool_calls LIKE '%walter_browse%'` also matches tool_describe / skill_view
  mentions — to prove an **invocation**, look for the exact tool name in the
  arguments of a tool_call, not in the raw row.

## 7. Source de vérité du schema exposé au LLM

The `WALTER_BROWSE_SCHEMA` constant (description + properties + required)
is exactly what the model sees. Inspect it via module-by-path (section 5) —
never rewrite it from memory.