# Kie provider migration patterns for stateful Workers

## Centralize model routing

For an application moving both media and reasoning from another provider to Kie:

- Verify live model IDs from `GET https://api.kie.ai/api/v1/playground/model-paths`.
- Put Gemini endpoint selection, Bearer auth, JSON parsing, and errors in one client module.
- Kie Gemini OpenAI-compatible endpoints are model-specific. Verified examples: `gemini-3.1-pro/v1/chat/completions` and `gemini-3-5-flash-openai/v1/chat/completions`.
- Preserve OpenAI message/tool-call shapes when the existing agent loop already consumes them.

## Defaults require code and data changes

Changing a hardcoded fallback does not migrate persisted routing:

1. Make Kie the no-route default in code.
2. Preserve the old provider only as an explicit configured fallback.
3. Add an idempotent database migration that inserts high-priority Kie defaults.
4. Normalize legacy model IDs such as `seedance-2` to provider-native `bytedance/seedance-2`.
5. Test no-route, legacy-route, and explicit-fallback cases separately.

## Media execution

- Images may be synchronously polled when the Worker request budget permits: `createTask` → `recordInfo` → parse `data.resultJson.resultUrls`.
- Videos should be submitted with `callBackUrl` and completed via webhook; do not hold a Worker request open while polling video.
- Cap image polling and treat optional sheets/storyboards as non-fatal where the pipeline can proceed without them.
- Seedance first/last-frame mode must omit `reference_image_urls`, `reference_video_urls`, and `reference_audio_urls`.

## Regression-test migration

Legacy test suites may encode the old provider in permissive fetch helpers. Use this sequence:

1. Add RED behavior tests that assert the exact Kie URL and request model.
2. Let the shared mock expose the real Kie request to focused tests first.
3. Only for legacy fixtures, adapt old Google-native `candidates[].content.parts[].functionCall` responses to OpenAI tool calls.
4. Never rewrite the outbound request model in the helper merely to satisfy stale assertions.
5. Assert that default flows observed Kie and did not observe the former provider.
6. Run targeted tests, a real Worker dry-run build, then the full suite; compare full-suite failures with the pre-migration baseline.

A pre-existing UI/source-regex test drift is not a provider regression. Fix failures caused by routing changes and report unrelated baseline failures separately.
