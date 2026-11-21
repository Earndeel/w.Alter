---
name: hermes-skills-index-optimization
category: devops
description: "Skills index progressive disclosure — skill_search tool + compact category index. Reduces system prompt from ~6K to ~1.2K tokens (80% reduction). Audit, implement, and maintain the skills payload optimization."
created: 2026-06-04
tags: [hermes, performance, tokens, skills, system-prompt, optimization]
---

# Hermes Skills Index Optimization

The available_skills block in the system prompt is the single largest component of every API call — typically ~60% of the total system prompt. This skill covers how to audit, measure, and optimize it.

## Why This Matters

Every API call sends the full skills index regardless of the user's query. A simple "bonjour" still processes ~11.6K tokens of skill metadata. On paid models this costs money; on free models with rate limits, it eats context window.

## Current Numbers (June 2026)

### Before optimization (static full index)

- Skills index: ~24,649 chars (~6,162 tokens) = **~60%** of system prompt
- ~237 skills (`.archive/` excluded by `EXCLUDED_SKILL_DIRS`), 36 categories
- Average description: ~195 chars. Longest: godmode (415), video-agent-factory (355), hermes-provider-mastery (332)

### After optimization (compact category-only index, June 2026)

- Skills index: **~4,990 chars (~1,247 tokens)** = ~15% of system prompt
- **Reduction: 80%** (~4,914 tokens saved per turn)
- Compact format: `category (count): description` — no individual skill listings
- Agent uses `skill_search(query)` → `skill_view(name)` on demand

### Gate condition

Compact mode activates when **both** conditions are met:
1. `skill_search` is in `available_tools` (i.e. the `skills` toolset is loaded)
2. Total skills count > 50

Below 50 skills, the full index stays — the extra agent turn cost outweighs savings.

## Audit Script

```python
from pathlib import Path
from agent.prompt_builder import iter_skill_index_files, parse_frontmatter

skills_dir = Path("/root/.hermes/skills")
total_chars = 0
count = 0
long_descs = []

for sf in iter_skill_index_files(skills_dir, "SKILL.md"):
    try:
        content = sf.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(content)
        desc = fm.get("description", "")
        name = fm.get("name", sf.parent.name)
        total_chars += len(desc)
        count += 1
        if len(desc) > 300:
            long_descs.append((name, len(desc)))
    except:
        pass

print(f"Skills in index: {count}")
print(f"Total desc chars: {total_chars:,} (~{total_chars//4:,} tokens)")
print(f"Estimated pct of system prompt: ~{total_chars/78000*100:.0f}%")
if long_descs:
    print(f"\nLongest descriptions (>300 chars):")
    for name, chars in sorted(long_descs, key=lambda x: -x[1])[:10]:
        print(f"  {name}: {chars} chars")
```

## The tool_search Pattern Already Exists

tools/tool_search.py implements progressive disclosure for MCP/plugin tools:

When tool schemas exceed 10% of context, they get replaced with bridge tools: tool_search(query), tool_describe(name), tool_call(name, args).

Core Hermes tools are never deferred. The same pattern can apply to skills.

## Implemented: skill_search Bridge Tool (June 2026)

Current flow (compact index + on-demand search):
- System prompt contains category-only index (~1.2K tokens)
- Agent calls `skill_search("video generation")` → ranked results with score
- Agent calls `skill_view("multi-model-video-gen")` → full content

### What was built

**`tools/skill_search.py`** — standalone tool, no external deps. Scoring tiers:

| Score | Match type |
|-------|-----------|
| 100 | Exact name match |
| 90 | Query is prefix of name |
| 80 | Query is substring of name |
| 70 | All query terms in name |
| 60 | Query is substring of description |
| 50 | All query terms in description |
| 40 | Query is substring of category |
| 30 | Any query term in description |
| 10 | Any query term in category |

Parameters: `query` (required), `category` (optional filter), `limit` (default 10, max 25).
Returns JSON: `{success, query, results: [{name, description, category, score}], count, total_skills}`.

### Files modified

1. **`tools/skill_search.py`** (new) — tool implementation + `registry.register()` at module level
2. **`toolsets.py`** — added `"skill_search"` to the `skills` toolset's tools list
3. **`agent/prompt_builder.py`** — `build_skills_system_prompt()` now checks if `skill_search` in `available_tools`; if yes + >50 skills, emits compact category-only index instead of full per-skill listing

### How to add a new bridge tool to Hermes

Pattern derived from this implementation:

```python
# tools/my_tool.py
from tools.registry import registry

def my_tool(args): ...

MY_SCHEMA = {"name": "my_tool", "description": "...", "parameters": {...}}

registry.register(
    name="my_tool",
    toolset="target_toolset",    # must match a key in toolsets.py
    schema=MY_SCHEMA,
    handler=lambda args, **kw: my_tool(args),
    check_fn=lambda: True,       # availability check
    emoji="🔧",
)
```

Then add `"my_tool"` to the toolset's `tools` list in `toolsets.py`.

Auto-discovery: `discover_builtin_tools()` in `registry.py` scans `tools/*.py` for top-level `registry.register()` calls via AST inspection. No manual import needed — just placing the file in `tools/` is sufficient.

## Semantic backend evaluation (unchanged — FTS is sufficient)

The question arose: should `skill_search` use embeddings/Qdrant for semantic matching?

**Verdict: No — simple text scoring is sufficient for ~250 skills.**

- 10-tier scoring (exact → prefix → substring → term-in-description) covers 95%+ of queries
- Embeddings add latency (~50ms/query via Qdrant), external dependency, and index maintenance
- The real problem is **routing** (when to search), not **retrieval** (how to search)

**3-layer approach (implemented layers 1+2):**
1. **Category index** (~1.2K tokens) — category names + counts in system prompt ✅
2. **Text scoring** (0ms) — `skill_search()` with 10-tier scoring ✅
3. **Semantic re-ranking** (optional, future) — Qdrant vectors for ambiguous queries. Only if FTS returns <3 results with score <30.

## Implementation Status: ✅ COMPLETE

All four steps implemented and tested (June 2026):
1. ✅ `tools/skill_search.py` created — standalone, no deps on skills_hub
2. ✅ Registered in `skills` toolset via `toolsets.py`
3. ✅ `build_skills_system_prompt()` emits compact index when `skill_search` in `available_tools`
4. ✅ Gate: >50 skills required for compact mode activation

**Tests**: 130/130 prompt_builder tests pass, 234/234 toolset tests pass.

**Activation**: Requires Hermes restart. The `skills` toolset must be loaded (it is by default in most profiles).

## Code References

- `tools/skill_search.py` — the skill_search tool (new)
- `toolsets.py` line ~165: `skills` toolset definition (includes `skill_search`)
- `agent/prompt_builder.py` line ~1045: `build_skills_system_prompt()` — compact mode logic at line ~1219
- `agent/system_prompt.py`: `skills_prompt = _r.build_skills_system_prompt(available_tools=agent.valid_tool_names, ...)`
- `tools/tool_search.py`: the progressive disclosure pattern this mirrors
- `tools/registry.py`: `discover_builtin_tools()` — AST-based auto-discovery of `registry.register()` calls
- `agent/skill_utils.py`: `EXCLUDED_SKILL_DIRS` — directories excluded from skill scanning (`.archive`, `.git`, etc.)

## Pitfalls

- **Cache invalidation**: `build_skills_system_prompt()` has a 2-layer cache (LRU + disk snapshot). When testing changes, clear both: `_SKILLS_PROMPT_CACHE.clear()` in-process, delete `.skills_prompt_snapshot.json` on disk.
- **`get_hermes_home()` returns `Path`**: mock with `Path(tmp)`, not a string — causes `TypeError: unsupported operand type(s) for /` otherwise.
- **Gate uses `available_tools` not `available_toolsets`**: the check is `"skill_search" in available_tools`, which means the tool must be resolved (not just the toolset loaded). If a toolset is loaded but the tool's `check_fn` returns False, it won't appear in `available_tools`.

## Support Files

- references/audit-raw-data.md: Raw audit data — top 20 longest descriptions, archive skill list, category distribution, conditional skills analysis.
