# ComfyUI custom node + frontend workflow loader

Use when a user needs a domain-specific workflow to appear inside the **original ComfyUI UI** rather than a separate dashboard.

## Custom node package shape

Create a directory under `ComfyUI/custom_nodes/<package_name>/`:

```text
custom_nodes/my_workflow_nodes/
  __init__.py
  web/
    workflow_loader.js
    my-workflow-editor.json
    my-workflow-api.json
```

In `__init__.py` expose:

```python
NODE_CLASS_MAPPINGS = {"MyNode": MyNode}
NODE_DISPLAY_NAME_MAPPINGS = {"MyNode": "My Node"}
WEB_DIRECTORY = "./web"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
```

ComfyUI serves `web/` files at:

```text
/extensions/<package_name>/<file>
```

Restart ComfyUI after adding node classes.

## Frontend loader extension

A minimal loader can import the app and call `app.loadGraphData()`:

```js
import { app } from "../../scripts/app.js";

const WORKFLOW_URL = "/extensions/my_workflow_nodes/my-workflow-editor.json";

async function loadWorkflow() {
  const response = await fetch(WORKFLOW_URL, { cache: "no-cache" });
  if (!response.ok) throw new Error(`Cannot load workflow: ${response.status}`);
  const workflow = await response.json();
  await app.loadGraphData(workflow);
  app.graph.setDirtyCanvas(true, true);
  if (app.canvas) app.canvas.setDirty(true, true);
}

app.registerExtension({
  name: "My.WorkflowLoader",
  async setup() {
    const button = document.createElement("button");
    button.textContent = "Load My Workflow";
    button.addEventListener("click", loadWorkflow);
    document.body.appendChild(button);

    const params = new URLSearchParams(window.location.search);
    if (params.get("workflow") === "my-workflow") {
      window.setTimeout(loadWorkflow, 900);
    }
  },
});
```

## Verification

- `GET /object_info/MyNode` returns the node schema.
- `GET /extensions/my_workflow_nodes/workflow_loader.js` returns JS.
- `GET /extensions/my_workflow_nodes/my-workflow-editor.json` returns editor-format JSON (`nodes`, `links`).
- POST API-format JSON to `/prompt`; require `node_errors == {}`.
- For headless UI checks, wait for the app to load and inspect DOM text for workflow-specific node titles. A splash-logo screenshot alone is not proof that the graph loaded.

## Pitfalls

- Editor format and API format differ. Use editor format with `app.loadGraphData()`; use API format for `/prompt`.
- Fallback/conditional branches can create dependency cycles when represented as executable links. Keep fallback metadata on nodes unless you can guarantee an acyclic graph.
- A workflow saved in `user/default/workflows/` may appear in the Load menu, but it will not auto-load by itself. Use a frontend extension or instruct the user to click Load/drag-drop.
