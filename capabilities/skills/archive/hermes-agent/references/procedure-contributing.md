## Contributor Quick Reference

For occasional contributors and PR authors. Full developer docs: https://hermes-agent.nousresearch.com/docs/developer-guide/

### Project Layout

```
hermes-agent/
├── run_agent.py          # AIAgent — core conversation loop
├── model_tools.py        # Tool discovery and dispatch
├── toolsets.py           # Toolset definitions
├── cli.py                # Interactive CLI (HermesCLI)
├── hermes_state.py       # SQLite session store
├── agent/                # Prompt builder, compression, display, adapters
├── hermes_cli/           # CLI subcommands, config, setup, commands
│   ├── commands.py       # Slash command registry (CommandDef)
│   ├── config.py         # DEFAULT_CONFIG, env var definitions
│   └── main.py           # CLI entry point and argparse
├── tools/                # One file per tool
│   └── registry.py       # Central tool registry
├── gateway/              # Messaging gateway
│   └── platforms/        # Platform adapters (telegram, discord, etc.)
├── cron/                 # Job scheduler
├── tests/                # ~3000 pytest tests
└── website/              # Docusaurus docs site
```

Config: `~/.hermes/config.yaml` (settings), `~/.hermes/.env` (API keys).

### Adding a Tool (3 files)

**1. Create `tools/your_tool.py`:**
```python
import json, os
from tools.registry import registry

def check_requirements() -> bool:
    return bool(os.getenv("EXAMPLE_API_KEY"))

def example_tool(param: str, task_id: str = None) -> str:
    return json.dumps({"success": True, "data": "..."})

registry.register(
    name="example_tool",
    toolset="example",
    schema={"name": "example_tool", "description": "...", "parameters": {...}},
    handler=lambda args, **kw: example_tool(
        param=args.get("param", ""), task_id=kw.get("task_id")),
    check_fn=check_requirements,
    requires_env=["EXAMPLE_API_KEY"],
)
```

**2. Add import** in `model_tools.py` → `_discover_tools()` list.

**3. Add to `toolsets.py`** → `_HERMES_CORE_TOOLS` list.

All handlers must return JSON strings. Use `get_hermes_home()` for paths, never hardcode `~/.hermes`.

### Adding a Slash Command

1. Add `CommandDef` to `COMMAND_REGISTRY` in `hermes_cli/commands.py`
2. Add handler in `cli.py` → `process_command()`
3. (Optional) Add gateway handler in `gateway/run.py`

All consumers (help text, autocomplete, Telegram menu, Slack mapping) derive from the central registry automatically.

### Agent Loop (High Level)

```
run_conversation():
  1. Build system prompt
  2. Loop while iterations < max:
     a. Call LLM (OpenAI-format messages + tool schemas)
     b. If tool_calls → dispatch each via handle_function_call() → append results → continue
     c. If text response → return
  3. Context compression triggers automatically near token limit
```

### Testing

```bash
source venv/bin/activate  # or .venv/bin/activate
python -m pytest tests/ -o 'addopts=' -q   # Full suite
python -m pytest tests/tools/ -q            # Specific area
```

- Tests auto-redirect `HERMES_HOME` to temp dirs — never touch real `~/.hermes/`
- Run full suite before pushing any change
- Use `-o 'addopts='` to clear any baked-in pytest flags

### Commit Conventions

```
type: concise subject line

Optional body.
```

Types: `fix:`, `feat:`, `refactor:`, `docs:`, `chore:`

### API Robustness Patterns

When hardening a tool function that calls an external HTTP API (TTS, image gen, STT, etc.), apply these layers in order of priority. The goal: the function never fails for transient reasons and handles input of any size.

**1. Retry with exponential backoff (mandatory first layer)**

Wrap the HTTP call in a retry loop. 3 attempts is usually enough. Backoff: 2s, 4s, 8s for timeouts/5xx; 4s, 8s, 16s for 429 rate limits. Do NOT retry on 4xx client errors except 429.

```python
import time as _time
max_retries = 3
for attempt in range(max_retries):
    try:
        response = requests.post(endpoint, json=payload, timeout=120)
    except requests.exceptions.Timeout:
        if attempt < max_retries - 1:
            wait = 2 * (2 ** attempt)
            logger.warning("Timeout (attempt %d/%d), retrying in %ds...", attempt+1, max_retries, wait)
            _time.sleep(wait)
            continue
        raise RuntimeError(f"API timed out after {max_retries} attempts")
    except requests.exceptions.ConnectionError as e:
        # Same pattern — retry, then raise on final attempt
        ...
    if response.status_code >= 500:
        # Retry on server errors
        ...
    elif response.status_code == 429:
        # Retry with doubled backoff (4s, 8s, 16s)
        ...
    elif response.status_code == 200:
        break
    else:
        break  # 4xx client errors: fail fast
```

Use `response.json()` parsing inside a try/except KeyError/IndexError to surface malformed responses cleanly.

**2. Automatic text chunking (for length-limited APIs)**

If the API has an input length limit (Gemini TTS: ~3000 chars, ElevenLabs: 5000 chars), add a chunking wrapper that:
- Splits at sentence boundaries (`.!?…`) using `re.split(r'(?<=[.!?…])\s+', text)`
- For sentences exceeding the limit, further split by word boundaries
- Generates audio/image per chunk, concatenates with ffmpeg/ImageMagick
- Short inputs pass through directly (no overhead)

Do NOT chunk by fixed character count — sentence-boundary splitting preserves natural pauses. Place chunking logic in a separate `_generate_X_chunked()` wrapper so the base function stays clean.

**3. Provider fallback (last resort)**

If all retries + chunking fail, fall back to an alternative provider (e.g., Gemini TTS → Edge TTS). Wrap the primary call in try/except, catch the broadest Exception, log the error, and route to the fallback. Raise a combined error only if the fallback is also unavailable.

```python
try:
    _generate_primary_chunked(text, output_path, config)
except Exception as primary_err:
    logger.warning("Primary failed (%s), falling back to secondary...", primary_err)
    try:
        _import_secondary()
    except ImportError:
        raise RuntimeError(
            f"Primary failed and secondary unavailable. Primary error: {primary_err}"
        ) from primary_err
    _generate_secondary(text, output_path, config)
```

**Testing the robustness:** after patching, test with `python3 -c "import ast; ast.parse(open('tools/tts_tool.py').read()); print('Syntax OK')"` then run a real call with a long text to verify chunking and fallback fire correctly.

### Key Rules

- **Never break prompt caching** — don't change context, tools, or system prompt mid-conversation
- **Message role alternation** — never two assistant or two user messages in a row
- Use `get_hermes_home()` from `hermes_constants` for all paths (profile-safe)
- Config values go in `config.yaml`, secrets go in `.env`
- New tools need a `check_fn` so they only appear when requirements are met
