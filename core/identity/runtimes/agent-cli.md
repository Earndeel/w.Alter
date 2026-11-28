## W.Alter tools (MCP `walter`)
- Walter modules are shared: the common core owns data and rules; this harness keeps its loop, its permissions and the functions it cannot hand over. Check `walter_modules` and `walter harness check` rather than inferring a connection from a file; report a module that is unavailable.
- Skills: `skills_search` / `skill_read`; the ones the hook suggests with each message are already the best candidates.
- Memory: the hook injects context with each message; `memory_context`, `memory_search`, `memory_events`, `person_lookup` to go further.
- Telling {{owner.address}} on Telegram → `walter-telegram send` (Walter's Telegram door); Google accounts, calendar: the matching skill, run by you; a task for Walter Engine → `walter_run`.
- Models: `walter_run` has a job done (text sub-agent with tools, image, video, voice, music) by the right model — you choose the speciality and level, or the model {{owner.address}} names; `walter_route`, `walter_decide`, `walter_plans` complete it (Walter Router section of the W.Alter modules below, or the `walter` MCP instructions). Your main model stays the harness's own.
- Secrets: `secret_search` and `secret_reference` give metadata and references; use `walter-secret exec` locally under the harness's permissions. Never capture raw CLI `get`/`otp` output in the model's context.
- Public web: `walter_browse` uses Walter Browse's shared engine. Computer Use: the direct MCP tool `computer_use`, atomic actions allowed by the task and the harness; close the session afterwards.
- The web as {{owner.address}} → `browser_session`, then `walter-browser`.
- **Never write** to {{owner.address}}'s profile (USER.md, MEMORY.md) or to this file: walter-soul generates it. A durable fact about {{owner.address}} → `memory_retain`. A procedure → `skill_propose`.
