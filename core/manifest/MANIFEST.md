# walter-core

**Role.** Connects W.Alter's modules to each runtime under the same tool names without replacing the runtime or its
permissions: the `walter` MCP server, the platform library (registry, paths, instance, presentation), runtime hooks,
and the core components (engine, identity, security, interfaces).

**Tools**
- `module_guide(path, depth="D1"|"D2"|"D3")`: documentation of W.Alter (`walter`), a module (`memory`) or a component
  (`memory/events`); each D2 lists its children's paths. `module_index(module, section)`: a module's live contents.
- `walter_health`: state of the stack; `walter_modules(module)`: technical declarations (contracts, dependencies,
  per-runtime limits, observed files).
- `walter_run(request, goal)`: delegate work to Walter Engine (delegated session under its policy).
- `walter_call(tool, arguments)`: call a W.Alter tool that is not in your list (`describe=true` gives its
  parameters).
- Native messaging: `beeper_read(operation="chats"|"messages"|"search"|"accounts"|"status", …)` reads the local
  Beeper server; on the engine, `beeper_send_message(chat_id, text, reply_to)` sends under its policy and disclosure
  check.
