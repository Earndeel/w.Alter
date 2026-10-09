# Stratified Cache Breakpoint Patch (Hermes)

Pattern for replacing Hermes' single-breakpoint cache injection with a stratified 3-breakpoint layout using the existing `{stable, context, volatile}` split from `build_system_prompt_parts()`.

## Target files

- `agent/system_prompt.py` — cache the parts dict on the agent for reuse
- `run_agent.py` — replace single-marker injection with stratified injection

## Step 1 — Cache the parts dict

In `agent/system_prompt.py`, `build_system_prompt()`:

```python
def build_system_prompt(agent: Any, system_message: Optional[str] = None) -> str:
    parts = build_system_prompt_parts(agent, system_message=system_message)
    agent._cached_system_prompt_parts = parts  # NEW: stash for stratified cache injection
    return "\n\n".join(p for p in (parts["stable"], parts["context"], parts["volatile"]) if p)
```

And in `invalidate_system_prompt()`:

```python
def invalidate_system_prompt(agent: Any) -> None:
    agent._cached_system_prompt = None
    agent._cached_system_prompt_parts = None  # NEW: keep in sync
    if agent._memory_store:
        agent._memory_store.load_from_disk()
```

## Step 2 — Replace single-marker injection

In `run_agent.py:4399-4405`, current code:

```python
# Inject cache_control on the last part of the system message.
for msg in prepared:
    if isinstance(msg, dict) and msg.get("role") == "system":
        content = msg.get("content")
        if isinstance(content, list) and content and isinstance(content[-1], dict):
            content[-1]["cache_control"] = {"type": "ephemeral"}
        break
```

Replace with:

```python
for msg in prepared:
    if isinstance(msg, dict) and msg.get("role") == "system":
        content = msg.get("content")
        if isinstance(content, list) and content:
            self._inject_stratified_cache_breakpoints(content)
        break
```

And add the method to `AIAgent`:

```python
def _inject_stratified_cache_breakpoints(self, content_blocks: list) -> None:
    """Pose up to 3 cache_control markers at stable/context/volatile boundaries.

    Anthropic caches each prefix independently (up to 4 breakpoints allowed).
    Ordering blocks stable -> context -> volatile means a change to volatile
    only invalidates the volatile prefix; the longer stable+context cache
    stays warm. TTL 1h on stable+context (rarely changes); TTL 5m on volatile.

    Fallback: if parts dict is absent (e.g. system_prompt built before this
    patch landed), preserve original single-marker behaviour.
    """
    parts = getattr(self, "_cached_system_prompt_parts", None)
    if not parts or not isinstance(content_blocks[0], dict):
        if isinstance(content_blocks[-1], dict):
            content_blocks[-1]["cache_control"] = {"type": "ephemeral"}
        return

    # Only stratify if the current single-block layout matches the
    # concatenated parts we cached. Defensive: if anything mutated the
    # content shape, fall back to single marker.
    if len(content_blocks) != 1:
        content_blocks[-1]["cache_control"] = {"type": "ephemeral"}
        return

    new_blocks = []
    stable = parts.get("stable") or ""
    context = parts.get("context") or ""
    volatile = parts.get("volatile") or ""

    if stable:
        new_blocks.append({
            "type": "text",
            "text": stable,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        })
    if context:
        new_blocks.append({
            "type": "text",
            "text": context,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        })
    if volatile:
        new_blocks.append({
            "type": "text",
            "text": volatile,
            "cache_control": {"type": "ephemeral"},  # default 5m
        })

    if new_blocks:
        content_blocks[:] = new_blocks
```

## Step 3 — Verify

1. Clear pyc cache: `find ~/.hermes/hermes-agent -name '*.pyc' -path '*agent*' -delete`
2. Restart gateway: `systemctl --user restart hermes-gateway`
3. Start a new session on Claude (Opus 4.7 via Kie or direct Anthropic).
4. After call #3 in agent.log, expect to see:
   - `cache=N/N (100%)` ratio maintained
   - Response usage shows `ephemeral_1h_input_tokens > 0` for stable+context portion
   - Response usage shows `ephemeral_5m_input_tokens > 0` for volatile portion only
5. Edit `MEMORY.md` mid-session: cache hit ratio should stay close to 100% because only the volatile prefix re-writes. Pre-patch, the entire prefix would invalidate.

## Rollback

Git-revert the two files, clear pyc, restart gateway. Single-marker behaviour resumes; no schema migration needed.

## Caveats

- If a downstream patch ever turns `system` content into a list with multiple text blocks before this injection runs (e.g. for tool-name prefixing in Claude Code OAuth mode), the `len(content_blocks) != 1` guard falls back to the single marker. That's safe but suboptimal — revisit when those code paths land.
- The `volatile` block contains the timestamp line. Hermes already uses date-only precision (not minute-level) so the volatile block is stable across an entire day — TTL 5m is enough; TTL 1h on volatile would only help if multiple turns happen within an hour without any Hindsight retention or memory write.
- For OpenRouter / Nous Portal Claude (envelope layout, `use_native_layout=False`), this patch does NOT apply — those gateways accept markers on message envelopes, not on inner content parts. The current single-marker injection already handles them; only branch this new code path when `use_native_layout=True`.
