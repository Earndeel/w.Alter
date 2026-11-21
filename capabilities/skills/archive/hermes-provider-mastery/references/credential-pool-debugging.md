# Credential Pool Debugging

When a provider has multiple API keys in its credential pool, Hermes selects one based on `credential_pool_strategies` (or `fill_first` by default). Diagnosing which key is actually active requires special techniques because Hermes redacts secret values.

## Diagnosis Workflow

### Step 1: Check Pool Order

**`hermes auth list <provider>`** (quickest):
```bash
hermes auth list gemini
# gemini (2 credentials):
#   #1  GEMINI_API_KEY       api_key env:GEMINI_API_KEY ←
#   #2  GOOGLE_API_KEY       api_key env:GOOGLE_API_KEY
```
The `←` marker indicates the active (priority-0) entry.

`fill_first` always uses priority 0 until it's exhausted (429/rate-limited).

### Step 2: Identify Which Key Is Which (Fingerprinting)

Hermes redacts secret values (`***`) in terminal output. To determine which env var holds which key, compare partial fingerprints (first 8 + last 4 chars) against known keys.

```bash
# Safe fingerprinting — shows first 8 + last 4 chars only
python3 -c "
with open('HERMES_DOT_ENV_PATH') as f:
    for line in f:
        if 'API_KEY' in line and '=' in line:
            k, v = line.strip().split('=', 1)
            print(f'{k}: {v[:8]}...{v[-4:]}')
"
```
Replace `HERMES_DOT_ENV_PATH` with the actual .env path.

**Why partial fingerprints work:** Gemini API keys are 39 chars. Comparing first 8 + last 4 gives 12 bits of identification with negligible collision risk, without exposing the full secret.

### Step 3: Verify Ground Truth (Adapter-Level Debug)

`hermes auth list` and `auth.json` show the pool state, but to confirm which key is ACTUALLY sent to the API, add a temporary debug print in the adapter's header-building method.

For Gemini (`agent/gemini_native_adapter.py`, ~line 873, in the headers dict construction):
```python
import sys; print(f"DEBUG_GEMINI_KEY: {self.api_key[:8]}...{self.api_key[-4:]}", file=sys.stderr, flush=True)
```

**Pitfall**: Place the print BEFORE the headers dict literal, not inside it — putting it inside the `{}` causes a `SyntaxError: ':' expected after dictionary key`.

Test with:
```bash
hermes chat -q "Say OK" -m gemini-3.5-flash --provider gemini -Q
```
Output will include `DEBUG_GEMINI_KEY: AIzaSyDQ...HgU4` confirming the active key.

**Remember to remove the debug line after verification.**

### Step 4: Fix

**Option A — Swap env var values in `.env`** so the desired key lands in the position `fill_first` picks (priority 0), then `hermes gateway restart`.

**Option B — Explicit strategy** in config.yaml:
```yaml
credential_pool_strategies:
  gemini: fill_first    # always use #1 until exhausted
  # or
  gemini: round_robin   # rotate across all credentials
```

## Critical: `hermes status` Is Misleading

`hermes status` displays the first matching env var from the **tuple order** in `auth.py`'s `api_key_env_vars` — NOT the one actually selected by the credential pool. For Gemini:
- Tuple order: `("GOOGLE_API_KEY", "GEMINI_API_KEY")` — GOOGLE first
- Pool priority: `GEMINI_API_KEY` = priority 0 (active)

`hermes status` shows `GOOGLE_API_KEY`'s value even though the pool uses `GEMINI_API_KEY`. **Never trust `hermes status` for credential pool verification.**

## Testing Providers Directly

Use `hermes chat -q` to test a specific model through the actual provider pipeline:
```bash
hermes chat -q "Say OK" -m gemini-3.5-flash --provider gemini -Q
```

Flags: `-q` = quiet (no TUI), `-m` = model, `--provider` = provider, `-Q` = one-shot (exit after reply).

**Note**: `delegate_task` does NOT have a model/provider parameter — it always uses the delegation config. To test a specific provider, use `hermes chat -q` instead.

## Common Pitfalls

1. **GEMINI_API_KEY vs GOOGLE_API_KEY**: Gemini provider reads BOTH as a credential pool. #1 is `GEMINI_API_KEY` (priority 0). If the freetier key is in `GOOGLE_API_KEY`, it's never reached with `fill_first`.

2. **Third mystery key**: Users often have a `GEMINI_API_KEY` from an old project that's neither their freetier nor paid key. Always fingerprint — don't assume.

3. **Paid key not in .env**: The user's paid key may be stored only in Google Cloud console or vault, not in `.env`. Check before assuming.

4. **Restart required**: Credential pool is read at startup. Changes need `hermes gateway restart` or `/reset`.

5. **Swapping `.env` values doesn't change pool priority**: The pool priority in `auth.json` is independent. You must swap which env var holds which key, not just change the priority.

6. **Config changes require `/reset` for current session**: Changing `delegation.model` or other config requires a new session (`/reset`) — the current session caches the old config at startup.
