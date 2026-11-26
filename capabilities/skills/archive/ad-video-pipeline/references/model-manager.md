## Model Manager UI (Dashboard)

Dashboard header has `⚙ Models` button → modal for CRUD on model configs from the browser.

**Features:**
- Dropdown to select existing model for editing
- "+ New Model" button with template (config.json pre-filled as `{"name":"", "endpoint":"fal-ai/"}`)
- 3 textareas: `config.json`, `prompt.md`, `schema.md`
- Save creates or updates, Delete with confirmation
- JSON validation on config.json before save

**Dashboard detail panel:** Tab renamed from "Kling AI" to "Generate". Includes model selector dropdown, Generate Payload / Submit / Sync buttons, and editable JSON textarea.

**API Endpoints for Model CRUD:**
- `GET /api/models` — list all (id injected from dirname)
- `GET /api/models/<id>` — read config + prompt + schema
- `POST /api/models` — create `{id, config, prompt, schema}`
- `PUT /api/models/<id>` — update partial fields
- `DELETE /api/models/<id>` — delete directory
