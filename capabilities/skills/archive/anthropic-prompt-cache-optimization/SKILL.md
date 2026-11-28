---
name: anthropic-prompt-cache-optimization
description: Optimize prompt caching across ALL providers — Anthropic explicit breakpoints, MiMo/DeepSeek/OpenAI automatic prefix caching, Gemini context caching. Stratified breakpoints, TTL selection, payload structure, multi-provider adapter patterns, and measurement. Use when sessions are running expensive and the cache is either off, single-breakpoint, invalidated by volatile content, or when routing to multiple providers with different caching mechanisms.
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [anthropic, claude, cache, prompt-caching, optimization, cost, hermes]
    related_skills: [kie-gemini-mastery, hermes-provider-mastery, hermes-context-management]
---

# Anthropic Prompt Cache Optimization

Class-level skill: how to structure payloads to maximize prompt-cache hits across ALL providers. Covers two mechanisms: (1) Anthropic explicit `cache_control` breakpoints (up to 4, TTL-controlled), and (2) automatic prefix caching on MiMo/DeepSeek/OpenAI where the server hashes KV-cache blocks and matches the longest common prefix. The universal principle is the same for both: **order blocks stable → volatile**.

## When to use

- Session cost on Claude is higher than expected and you suspect cache misses
- Hermes shows `cache=0/N` or low hit ratio in `agent.log` API call lines
- You're adding a new third-party Anthropic-compatible gateway and need to verify caching works
- You need to decide between TTL 5m vs 1h, or whether to stratify with multiple breakpoints
- Volatile content (memory, timestamps, dynamic context) is invalidating an otherwise stable prefix
- You're building a multi-provider system and need to optimize cache for Anthropic AND auto-prefix providers (MiMo, DeepSeek, OpenAI) simultaneously
- MiMo/DeepSeek returns 422 or behaves unexpectedly — check that `cache_control` headers aren't leaking into the request

## Core mental model

Anthropic caches **prefixes**, not arbitrary ranges. Each `cache_control` marker tells the server "cache everything up to and including this block". Up to **4 breakpoints** allowed per request. The server picks the longest matching cached prefix automatically — you don't manage lookups.

Consequence: order blocks from **most stable → most volatile**, left to right. Put markers at the boundaries between volatility tiers.

Pricing ratios (standard Anthropic, replicated by passthrough providers like Kie):

| Operation | Ratio vs input |
|---|---|
| Cache WRITE 5m | 1.25× |
| Cache WRITE 1h | 2.00× |
| Cache READ | **0.10×** |

Break-even: cache READ pays for the WRITE after **~2 reads** (5m) or **~10 reads** (1h). Anything reused more than that is pure win.

## Stratification pattern (3–4 breakpoints)

For an agent system prompt with the standard Hermes structure:

```
┌─ BLOC 1 (never invalidated)        : SOUL + tool-use protocol      ← cache_control #1, TTL 1h
├─ BLOC 2 (session-stable)            : tool schemas + skills index   ← cache_control #2, TTL 1h
├─ BLOC 3 (rare invalidation)         : USER.md + MEMORY.md           ← cache_control #3, TTL 5m
├─ BLOC 4 (volatile)                  : Hindsight + date + meta       ← cache_control #4, TTL 5m
├═══════════════════════════════════════════════════════════════════
│ Conv history (messages)
│   ...
│   [optional: cache_control on second-to-last user message for history caching]
└─
```

**Why this works**: when volatile (BLOC 4) changes, the server falls back to the longest matching prefix that's still valid — BLOC 1+2+3. You only re-pay the volatile portion + a fresh write of BLOC 4. BLOCS 1+2+3 stay cached at the READ rate.

Naive single-breakpoint at the end of system: any change to volatile invalidates everything — full cache rewrite every turn.

## TTL selection

- **TTL 5m (default)**: high-frequency turns (active agent loop). Cheap to write (1.25×), but expires fast.
- **TTL 1h**: interactive sessions with human pauses (TUI, voice, chat). Costs 2× write once, then survives coffee breaks.

Rule of thumb: if a session sees ≥2 calls per hour but with gaps >5min, TTL 1h on stable blocks is cheaper overall.

## Hermes-specific implementation

### Current state (as of v0.18.0, 2026-07-04)

Upstream now ships a proper caching module — the older per-adapter description below is historical:

- `agent/prompt_caching.py:49` — `apply_anthropic_cache_control(api_messages, cache_ttl, native_anthropic)` implements the **system_and_3** strategy: up to 4 breakpoints = system prompt + last 3 non-system messages, all at the same TTL.
- Called from `agent/conversation_loop.py:~884`, gated on `agent._use_prompt_caching` (set by `anthropic_prompt_cache_policy()` in `agent/agent_runtime_helpers.py:1443`).
- TTL comes from `agent._cache_ttl` (config key `agent.cache_ttl`, default `5m`, read in `agent_init.py:519-526`).
- `conversation_loop.py` also normalizes whitespace + tool-call JSON (sorted keys, compact separators) on the API copy for bit-perfect prefix matching — benefits auto-prefix providers too.
- `_compute_threshold_tokens` (`context_compressor.py:912`) floors at MINIMUM_CONTEXT_LENGTH and subtracts the `max_tokens` output reservation — effective input budget is `context_length - max_tokens`.

### Diagnostic signature: frozen cache-read value (observed 2026-07-04, OpenRouter Claude)

If `agent.log` shows the SAME cache-read number across many calls while input grows:

```
call #2: in=56113 cache=36281/56113 (65%)
call #5: in=61496 cache=36281/61496 (59%)
call #8: in=64461 cache=36281/64461 (56%)
```

only the **system prompt** breakpoint is producing reads — the message-level (last-3) breakpoints are not caching incrementally. Prime suspect on OpenRouter: `agent.cache_ttl: 1h`. The 1h TTL requires Anthropic's extended-cache-ttl beta header, which OpenRouter may not relay for message-level markers. Fix: set `cache_ttl: 5m` (also halves write cost: 1.25× vs 2×) and re-measure. Healthy multi-turn sessions show the read value GROWING turn over turn and hit ratio climbing toward 85-90%.

### OpenRouter 402 "can only afford N tokens"

`402: You requested up to 128000 tokens, but can only afford X` = max_tokens is UNCAPPED. Hermes requested the model's max output (128K) and OpenRouter pre-reserves credits for the full reservation against the account balance. NOT a payload-size problem. Fix: set a global `agent.max_tokens` cap (16-32K covers virtually all real agent outputs; typical observed outputs <1K). Bonus: a bounded max_tokens improves the compressor's effective-input-budget math.

### Local patches don't survive `hermes update` — verify before diagnosing

Before diagnosing compressor/cache behaviour, check whether local optimization patches are still applied: `cd ~/.hermes/hermes-agent && git apply --check ~/.hermes/patches/compression-optimization.patch` — if the check SUCCEEDS, the patch is NOT applied (it was silently dropped by an update) and the stock code is running. Re-apply via `~/.hermes/patches/apply-patches.sh`. This exact scenario happened 2026-07-04: the cache-aware compressor patch had reverted to stock without any error.

### Historical state (2026-06-06, pre-v0.18)

- `agent/agent_runtime_helpers.py:1153-1255` — `anthropic_prompt_cache_policy()` decides whether to cache based on provider + api_mode + model. Returns `(should_cache, use_native_layout)`.
  - Returns `(True, True)` for native Anthropic, third-party Anthropic-wire gateways (Kie/Claude, MiniMax, Zhipu).
  - Returns `(True, False)` for OpenRouter/Nous Portal Claude, OpenCode/Alibaba Qwen (envelope layout).
- `run_agent.py:1174` — `_anthropic_prompt_cache_policy()` (instance method that wraps `agent_runtime_helpers.anthropic_prompt_cache_policy`, line 1153). Decides should_cache + native_layout for this request.
- **Single breakpoint injection happens inside the transport adapters**, not at run_agent.py:4399. Line 4399 is `_qwen_prepare_chat_messages` — Qwen-specific path, NOT Anthropic. Confirmed live 2026-06-06: patching 4399 affects Qwen only.
- For native Anthropic layout, the marker placement is in `agent/anthropic_adapter.py` around lines 2035-2060 (where `system_prompt` is converted to a list of content blocks and `cache_control` markers are preserved per block). For envelope layout (OpenRouter/Nous Portal/Qwen-on-OpenAI-wire), placement is in the chat-completions message builder and `_qwen_prepare_chat_messages`.
- `agent/agent_runtime_helpers.py:1153` — `anthropic_prompt_cache_policy()` decides whether to cache. Returns `(should_cache, use_native_layout)`.
- `agent/anthropic_adapter.py:2033-2066` — converts system prompt to list of content blocks and **preserves** any `cache_control` markers already on those blocks. This is where stratified markers must be present BEFORE the call reaches.
- `agent/system_prompt.py:61-344` — `build_system_prompt_parts()` produces `{stable, context, volatile}` dict — natural boundaries for stratification.
- ⚠️ **`run_agent.py:4399-4405` is Qwen-specific** (`_qwen_prepare_chat_messages`), NOT the Anthropic path. Verified 2026-06-06: search for `cache_control` in `run_agent.py` returns Qwen handlers; Anthropic injection happens upstream in the system prompt builder + adapter conversion.
- The single `cache_control = {"type": "ephemeral"}` marker injection for Anthropic happens implicitly via `build_system_prompt()` returning a string today — to stratify, the system prompt builder must return a **list of blocks with cache_control already on them**, then `anthropic_adapter._convert_system_prompt()` preserves them.
- `agent/transports/anthropic.py:160-169` — extracts `cache_read_input_tokens` + `cache_creation_input_tokens` from response.

## Reference material

- `references/stratified-breakpoint-patch.md` — full Anthropic breakpoint patch pattern.
- `references/multi-provider-cache-adapter.md` — provider branching for explicit vs auto-prefix cache.
- `references/measurement-recipe.md` — manual cache measurement probe.
- `references/codex-responses-input-last-cache-audit.md` — Codex/OpenAI Responses payload ordering audit showing why dynamic `input` must come after stable tools for auto-prefix cache.

Core idea: replace the single-marker injection with a function that:
1. Reads `agent._cached_system_prompt_parts` (cache the dict during `build_system_prompt`)
2. Splits the single system text block into 3 explicit blocks (stable / context / volatile)
3. Places `cache_control` on each block, with TTL 1h on stable+context and 5m on volatile

## Multi-provider adapter pattern

For systems that route to multiple providers (Anthropic + MiMo + DeepSeek), the payload must be built once and adapted per provider. See `references/multi-provider-cache-adapter.md` for the full decision tree and code patterns.

## Two caching mechanisms (compared)

### Mechanism A: Explicit breakpoints (Anthropic, Kie, MiniMax, Zhipu)
- You place `cache_control` markers on specific content blocks (up to 4)
- Server caches each marked prefix independently
- TTL-controlled (5m default, 1h for stable blocks)
- Advantage: independent block caching — if volatile block changes, earlier blocks stay cached at READ rate
- Pricing: WRITE 1.25× (5m) / 2× (1h), READ 0.1×

### Mechanism B: Automatic prefix caching (MiMo, DeepSeek, OpenAI, Gemini)
- Server automatically hashes KV-cache blocks token-by-token
- No `cache_control` headers — you control caching only through **payload ordering**
- Longest common prefix match: if the first N tokens are identical between two requests, everything up to token N is a cache hit
- Single TTL per provider (you don't control it)
- Advantage: zero configuration — just order your payload correctly
- MiMo pricing: $0.0036/M tokens on cache hit (~99% savings vs input)

### What's the same, what's different

| | Anthropic (A) | Auto-prefix (B) |
|---|---|---|
| **Cache trigger** | Explicit markers | Automatic hash match |
| **Control** | You choose what + TTL | Server decides, you control ordering |
| **Independent blocks** | ✅ each block cached separately | ❌ prefix is sequential, any divergence breaks suffix |
| **99% of the time** | Same result | Same result |
| **When volatile mid-prefix changes** | Earlier blocks still READ | Everything after divergence recalculated |

**Key insight**: the stable→volatile ordering is the **universal invariant** for both mechanisms. For Anthropic, breakpoints give finer control on top of that ordering. For auto-prefix providers, the ordering IS the only control.

## Universal payload ordering (all providers)

```
Stable ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━▶ Dynamique

 system    tools/cache metadata    context/history summaries    raw tail    latest input
  prompt       (schemas)              (semi-static → dynamic)       (small)      (volatile)
```

This order is optimal for ALL providers because:
- **Anthropic**: place breakpoints at tier boundaries → each tier cached independently.
- **MiMo/DeepSeek/OpenAI/Codex**: the stable prefix matches across turns → cache hit on ~80%+ of system prompt and tool schema payload.
- **OpenAI Responses/Codex**: make sure the JSON body order also follows this rule; if `input` appears before `tools`, the latest user message breaks the prefix before the large stable tool schema block. Put dynamic `input` last.

**Critical**: never inject dynamic content (timestamps to minute precision, random IDs, fresh memories, latest user input) into early positions. A single differing token at position N invalidates the prefix from N onward for auto-prefix providers.

## Provider compatibility matrix

| Provider | Route | Cache supported | Layout | Notes |
|---|---|---|---|---|
| Anthropic direct | `api.anthropic.com` | ✅ explicit | native (inner blocks) | Reference impl — 4 breakpoints, TTL control |
| Kie.ai `/claude` | `api.kie.ai/claude` | ✅ explicit | native | Passthrough pricing, 1h TTL supported |
| MiniMax `/anthropic` | `api.minimax.io/anthropic` | ✅ explicit | native | 0.1× read pricing documented |
| Zhipu GLM | varies | ✅ explicit | native | Anthropic-compatible |
| OpenRouter Claude | `openrouter.ai` | ✅ explicit | envelope (top-level) | OpenAI-wire, looser layout; pass-through of cache_control markers |
| Nous Portal Claude | `nousresearch.com` | ✅ explicit | envelope | Same as OpenRouter |
| **MiMo V2.5 Pro** | `api.mimo.com` OR OpenRouter | ✅ **auto-prefix** | chat completions (string) | Server-side KV hash. **Do NOT send cache_control** — causes 422 or silent breakage. Just order payload stable→volatile. $0.0036/M read. |
| **DeepSeek** | `api.deepseek.com` OR OpenRouter | ✅ **auto-prefix** | chat completions (string) | Same as MiMo. Automatic, no headers needed. |
| **OpenAI** | `api.openai.com` OR OpenRouter | ✅ **auto-prefix** | chat completions (string) | Auto-caching for prompts >1024 tokens. No explicit markers on standard path. |
| **Gemini AI Studio** | `generativelanguage.googleapis.com` | ✅ **context caching API** | separate endpoint | Create cachedContent first, then reference by ID. Different mechanism entirely. |
| Kie.ai Gemini/GPT routes | `/gemini-*`, `/chat/gpt-*` | ❌ | n/a | Returns 422 if you send cache_control |
| Alibaba Qwen (OpenCode) | DashScope | ✅ (Qwen-specific) | envelope | Different family, same marker mechanism |

## Measurement & verification

In Hermes `agent.log`, every API call logs cache usage:

```
API call #N: model=claude-opus-4-7 provider=kie in=37958 out=399 total=38357 latency=16.4s cache=37958/37958 (100%)
```

Format: `cache=<read>/<input> (<ratio>%)`. A healthy session shows `(100%)` from call #2 or #3 onward (call #1 is always a fresh write).

For a manual probe outside Hermes, use the 3-call recipe in `references/measurement-recipe.md` — derives exact pricing from `credits_consumed` + `usage` block.

## CRITICAL BUG: Compressor blind to cached tokens (discovered 2026-06-06)

The Hermes context compressor (`context_compressor.py`) uses `usage.prompt_tokens` from the API response to decide whether to compress. With Anthropic prompt caching, the provider reports `prompt_tokens` as **non-cached input tokens only** (e.g. ~46 tokens), NOT the full payload size (~95K tokens). This means:

- `should_compress()` (line 728) sees `tokens=46 < threshold=100000` → never compresses
- `should_defer_preflight_to_real_usage()` (line 698) sees `last_real_prompt_tokens=46 < threshold` → defers even when rough estimate says 119K
- The user must manually trigger `/compact` to compress, defeating the purpose

**Root cause**: `update_from_response()` at line 686 sets `self.last_prompt_tokens = usage.get("prompt_tokens", 0)` — this is the non-cached portion only. The real total is `prompt_tokens + cache_read_input_tokens + cache_creation_input_tokens`.

**Fix** (3 lines in `context_compressor.py:684-690`):
```python
def update_from_response(self, usage: Dict[str, Any]):
    # Include cached tokens in the total so compression triggers correctly
    cache_read = usage.get("cache_read_input_tokens", 0) or usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
    cache_create = usage.get("cache_creation_input_tokens", 0)
    raw_prompt = usage.get("prompt_tokens", 0)
    self.last_prompt_tokens = raw_prompt + cache_read + cache_create
    # ... rest unchanged
```

**Impact observed**: user session hit 119K tokens without auto-compression. CSV data showed 95K avg cache_read/call × 100 calls = $15.86 billed in one session. The compressor thought payload was 46 tokens.

**Verification**: after patching, check `agent.log` for `compression triggered` messages. The threshold is `context_length * 0.50` = 100K for Opus 4.7 (200K context).

## Payload composition (measured 2026-06-06)

Real breakdown of a typical Hermes+W.Alter session on Claude Opus 4.7:

| Component | Tokens | % of 95K avg |
|---|---|---|
| Conversation history | ~68K | 72% |
| Skills index (268 skills) | ~12K | 13% |
| Tool schemas (37 tools) | ~11K | 12% |
| Hindsight injection | ~875 | 1% |
| System prompt template | ~855 | 1% |
| MEMORY + SOUL + USER | ~1.2K | 1% |

**Key insight**: the conversation history is 72% of the payload — cache stratification helps the 28% stable portion, but compression of the growing history is what really matters. The two optimizations are complementary, not alternatives.

## Pitfalls

1. **Don't put `cache_control` on `thinking` blocks** — strips signature, request rejected. Hermes already filters this in `anthropic_adapter.py:1985`.
2. **Volatile content inside the cached prefix kills the cache** — timestamps to minute precision, fresh Hindsight memories, random session IDs. Either move them outside the breakpoint or stratify.
3. **OpenAI-wire routes ≠ Anthropic-wire routes** for cache. Kie's `/claude` works; Kie's `/gemini-*` and `/chat/gpt-*` do not.
4. **System prompt rebuild invalidates cache**. Hermes caches `_cached_system_prompt` for the session and only rebuilds after compression — preserve this invariant when patching.
5. **4 breakpoints is the hard cap** per Anthropic. Don't try to stratify beyond that.
6. **Cache scope is per-API-key + per-organization**, not global. Cross-session cache hits only work within the same account.
7. **Date-precision matters in the prompt**. Hermes uses date-only (not minute-precision) in the timestamp line for this reason — see `agent/system_prompt.py:325-331`.
8. **Multiple injection sites in run_agent.py** — there are at least three places that set `cache_control: ephemeral`: Anthropic-native path, OpenRouter envelope path, Qwen path (`_qwen_prepare_chat_messages` ~line 4399, `_qwen_prepare_chat_messages_inplace` ~line 4434). Patching one and missing the others leaves the others as single-breakpoint and creates inconsistent caching across providers. Grep all sites before applying a stratification patch.
9. **Patching `run_agent.py` is in-tree and gets overwritten by `hermes update`** — same pitfall pattern as `hermes-provider-mastery`. If you go this route, save the diff under `~/.hermes/patches/` and add a re-apply hook.
10. **Measure before patching** — when the user asks for cache optimization, run an audit of the live system first: read recent `agent.log` API call lines for actual `cache=R/I (ratio%)` values, dump the latest `request_dump_*.json` to confirm whether system is currently a string or list of blocks, and check the user's billing dashboard if accessible. A 30-line measurement script beats an hour of speculative patching, and the user will explicitly ask for evidence before approving a core patch. The audit numbers are also what justifies the patch to the user — without them the request to touch core code looks reckless.
11. **NEVER send `cache_control` to MiMo, DeepSeek, or OpenAI** — these providers use automatic prefix caching. Sending `cache_control` headers/markers causes 422 errors (MiMo) or silent breakage (LiteLLM #19923). The adapter must branch: explicit markers for Anthropic-compatible providers, plain string for auto-prefix providers. If you're building a multi-provider payload system, the `cache_control` injection must be gated on provider type.
12. **Auto-prefix providers need `content: "string"` not `content: [blocks]`** — the Anthropic wire format uses `content: [{"type": "text", "text": "...", "cache_control": {...}}]`. MiMo/DeepSeek/OpenAI expect `content: "plain string"`. Sending the block-list format to a chat-completions endpoint breaks parsing. If you have a list of blocks, join them with `"\n\n"` before sending to non-Anthropic providers.
13. **Mid-prefix change penalty on auto-prefix providers** — with Anthropic breakpoints, if BLOC 2 (context) changes mid-session, BLOC 3+4 (volatile + messages) can still cache independently. With auto-prefix, the entire suffix after the divergence point is recalculated. In practice this rarely matters (context doesn't change mid-session), but it's the theoretical advantage of explicit breakpoints.

## Related skills

- `kie-gemini-mastery` — Kie.ai-specific provider setup; references this skill for cache details.
- `hermes-context-management` — diagnosing context bloat, compression failures. Cache optimization complements compression.
- `hermes-provider-mastery` — provider lifecycle and configuration; payload patches for non-Anthropic providers.
- `model-id-lookup` — verify model availability on OpenRouter before routing; MiMo models have specific platform constraints.
