# Serverless secret-scope matrix

| Layer | Example evidence | What it proves | What it does not prove |
|---|---|---|---|
| Resource catalog | Model/endpoint appears in authoritative catalog | Requested resource exists | Credentials or runtime work |
| Local process | Bounded request succeeds using local vault/env | Local credential path works | Deployed secret matches |
| Control plane | Secret-list output contains expected binding name | Binding metadata exists | Secret value is valid |
| Build/dry-run | Worker bundles with expected bindings | Code and config compile | Provider accepts authentication |
| Deployed runtime | Remote smoke request succeeds through deployed code | End-to-end path works | Unrelated routes are healthy |

## Minimal smoke checklist

1. Use the exact production model/endpoint and parameter shape.
2. Bound token, compute, and monetary cost.
3. Do not expose secret material in logs or responses.
4. Capture HTTP status, served resource/model ID, finish state, and usage only.
5. For tool-capable models, verify a harmless dummy tool call rather than trusting text generation alone.
6. For planners, verify the required structured-output schema.
7. If the local probe fails but a deployed secret exists, label the deployed runtime **untested**, not broken.
8. Obtain deployment approval before exercising a cloud Worker with changed code.

## Common interpretations

- `401`: authentication path failed or no credential reached the provider.
- `402`: account/credit path failed; resource existence may still be valid.
- `403`: credential lacks permission, policy blocks the request, or provider access is restricted.
- `404`/model-not-found: re-check exact resource ID against the live catalog.
- `400`: inspect parameter compatibility before blaming authentication.
