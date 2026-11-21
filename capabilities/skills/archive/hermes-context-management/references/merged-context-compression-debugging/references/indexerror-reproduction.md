# ContextCompressor IndexError — Crash Trace

Bug location: `agent/context_compressor.py`, triggered at line 2808 inside `compress()`.

## Step-by-step crash path

Given 10 messages where messages[1..9] are all `role=tool`:

1. `_protect_head_size(messages)` → 1 (system prompt only, protect_first_n=0)
2. `_align_boundary_forward(messages, 1)`:
   - messages[1] = "tool" → idx=2
   - messages[2] = "tool" → idx=3
   - ...
   - messages[9] = "tool" → idx=10
   - 10 < 10 is False → returns **10** = `compress_start`

3. `_find_tail_cut_by_tokens(messages, head_end=10)`:
   - `n = 10`, `cut_idx = 10`
   - Token walk: `range(9, 9, -1)` → empty, `cut_idx` stays at 10
   - `_align_boundary_backward(messages, 10)`: 10 >= 10 → returns 10
   - `_ensure_last_user_message_in_tail(messages, 10, head_end=10)`:
     - `_find_last_user_message_idx(messages, head_end=10)`:
       - `range(9, 9, -1)` → empty → returns -1
       - -1 < 0 → returns `cut_idx` = 10
   - `_ensure_last_assistant_message_in_tail` → same → returns 10
   - **Line 2686**: `return max(10, 10 + 1)` = **11** → compress_end

4. Guard at line 2781: `10 >= 11` → **False** → proceeds past guard

5. `_find_latest_context_summary(messages, start=1, end=11)`:
   - range(10, 0, -1): idx = 10
   - **messages[10]** → IndexError: list index out of range

## Fix location

`agent/context_compressor.py`, line 2686:
```python
# Bug:
return max(cut_idx, head_end + 1)

# Fix:
return min(max(cut_idx, head_end + 1), len(messages))
```

With the fix, `compress_end = min(11, 10) = 10`. Then `compress_start (10) >= compress_end (10)` → True → early return with no-op.
