# Desktop picker: presentation groups over heterogeneous transports

Use this pattern when the user wants one vendor folder even though its models use different Hermes providers or wire protocols.

## Key distinction

Do **not** collapse runtime providers merely because they share a vendor name. Keep protocol-correct providers internally, then merge them only in the Desktop `model.options` payload.

## Implementation pattern

1. In `tui_gateway/server.py`, post-process the result of `build_models_payload()`.
2. Provider rows use `slug`, not `id`.
3. Model collections in this payload are lists of model-ID strings, not `{id, name}` objects.
4. Rename the retained presentation row, replace its `models` list with the exact requested order, update `total_models`, and filter transport-only rows by `slug`.
5. In the model-switch RPC path, translate `(presentation_slug, model_id)` to the real provider slug before calling `switch_model()`.
6. Keep ordinary models on the retained provider and add overrides only for models requiring another transport.

Example routing shape:

```python
if explicit_provider == "vendor-group":
    explicit_provider = {
        "responses-model": "vendor-responses",
        "cli-model": "vendor-cli",
    }.get(model_input, explicit_provider)
```

## Verification

Invoke the registered `model.options` handler directly for both default and `include_unconfigured=True` payloads. Assert:

- exactly one presentation row exists;
- its label and ordered model list are exact;
- hidden transport rows are absent;
- Python compilation succeeds;
- provider/runtime tests pass.

A successful code edit is not proof that the running Desktop process loaded it. Apply via a safe service reload/restart only when permitted; otherwise state precisely that it takes effect on the next restart. Never terminate unrelated user processes merely to refresh UI state.
