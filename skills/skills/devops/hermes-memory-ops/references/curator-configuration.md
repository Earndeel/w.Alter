# Curator Configuration — Tested Patterns

## Model Selection for LLM Consolidation

The curator's LLM pass (`curator.consolidate: true`) requires a model with strong reasoning + reliable tool calling. Tested configurations:

| Model | Provider | Result | Notes |
|-------|----------|--------|-------|
| GPT 5.5 | openai-codex (OAuth) | ✅ Best | 24 tool calls, 173s, 17 skills archived correctly |
| Gemini 3.5 Flash | gemini (free key) | ⚠️ 503 | Overloaded, high demand |
| Gemini 3-5-flash (dash) | gemini | ❌ 404 | Wrong model ID format |
| Claude Opus 4.8 | kie | ❌ 403 | PermissionDeniedError — key blocked |
| Gemini 2.5 Flash | gemini | Not tested | Stable alternative |

**Key finding:** Gemini model IDs use dots (`gemini-3.5-flash`), not dashes (`gemini-3-5-flash`).

## Configuration Path

```yaml
# Canonical aux task slot (preferred)
auxiliary:
  curator:
    provider: openai-codex
    model: gpt-5.5
    timeout: 600

# Legacy (deprecated, still works)
curator:
  auxiliary:
    provider: openai-codex
    model: gpt-5.5

# Consolidation toggle
curator:
  consolidate: true   # off by default
```

Precedence: `auxiliary.curator.*` > `curator.auxiliary.*` > main `model.*`

## Safe Workflow

1. Always `--dry-run --consolidate` first
2. Review the `run.json` and `REPORT.md` in `~/.hermes/logs/curator/`
3. Verify 0 tool calls = model couldn't access tools (setup issue)
4. Enable live: `hermes config set curator.consolidate true`
5. Run once manually: `hermes curator run`
6. Disable if results are poor: `hermes config set curator.consolidate false`

## What the Consolidation Pass Does

- Scans 100+ skills for prefix/domain clusters
- Merges narrow skills into class-level umbrellas via `skill_manage(action=patch/create)`
- Archives absorbed skills via `skill_manage(action=delete, absorbed_into=<umbrella>)`
- Respects pinning (never touches pinned skills)
- Produces YAML summary with `consolidations:` and `prunings:` lists
