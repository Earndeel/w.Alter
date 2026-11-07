# Hermes Desktop picker integration for Kie GPT-5.6 Sol

Use this when a Kie model must expose provider-specific reasoning levels directly in the Hermes Desktop `/model` menu.

## Verified identifiers and transport

- Hermes provider slug: `kie-gpt`
- Kie model ID: `gpt-5-6-luna`
- User-facing name: `GPT 5.6 Sol`
- Responses base URL: `https://api.kie.ai/codex/v1`
- Hermes accepts `minimal`, `low`, `medium`, `high`, `xhigh`, and `max` in `VALID_REASONING_EFFORTS`; do not collapse `xhigh` and `max` in UI when the provider exposes both.

## Desktop implementation pattern

1. Keep the real API model ID unchanged. Add the friendly name in `apps/desktop/src/lib/model-status-label.ts`, not in provider configuration.
2. Keep provider/model-specific effort options in `apps/desktop/src/app/shell/model-edit-submenu.tsx`.
3. Match both provider and model (`kie-gpt` + `gpt-5-6-luna`) before exposing the Sol-specific list:
   - `low`
   - `medium`
   - `high`
   - `xhigh`
   - `max`
4. Persist the selected value through the existing `setModelPreset` / `config.set` path. Do not create fake model IDs such as `gpt-5-6-luna-high`.
5. Preserve generic effort options for other providers; capability support is provider/model dependent.

## Verification

Run all three layers:

```bash
# Provider and parser contract
./venv/bin/pytest -q tests/test_hermes_constants.py tests/agent/test_kie_responses_provider.py

# Focused desktop behavior
cd apps/desktop
npm run test:ui -- src/lib/model-status-label.test.ts src/app/shell/model-edit-submenu.test.tsx
npm run typecheck
npm run build
```

Add tests for:

- the exact provider/model matcher;
- `GPT 5.6 Sol` display formatting;
- distinct labels for `xhigh` and `max`;
- successful desktop production build.

## Pitfalls

- The compact status label previously rendered `xhigh` as `Max`; that destroys the distinction when both levels exist. Map `xhigh` to `XHigh` and `max` to `Max`.
- A successful backend provider test does not prove the Desktop picker exposes the choices. Verify backend parser, UI tests, typecheck, and production build separately.
- Source changes alone are not a deliverable for Desktop work; produce and verify the renderer build.
