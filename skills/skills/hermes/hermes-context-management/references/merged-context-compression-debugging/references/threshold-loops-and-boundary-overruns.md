# Threshold loops, boundary overruns, and runtime verification

Use this reference when a Hermes conversation repeatedly displays **Summarizing thread**, performs pre-API compression on nearly every tool turn, or raises an `IndexError` during boundary selection.

## Diagnose in this order

1. **Measure runtime behavior before naming a cause.** Extract the context window, requested `max_tokens`, configured `compression.threshold`, minimum threshold, and every `Pre-API compression: ~N tokens` event.
2. **Read the persisted config separately.** Do not infer the active threshold or output budget from model capability metadata.
3. **Call the source resolver separately.** Compare its context-length result with runtime logs; a long-lived agent may retain metadata from an earlier model/session.
4. **Check provider documentation separately.** Provider `/models`, Hermes source metadata, and upstream model documentation may disagree. Record all three; do not silently choose the largest value.
5. **Compute the effective trigger with the implementation's actual formula**, including the minimum threshold floor. A low percentage can collapse to the floor rather than the naive percentage.
6. **Quantify the proposed threshold against observed events.** Count how many historical compression events would still trigger at the proposed value; this is stronger than saying it “should help.”

## Repeated-compaction mechanism

A loop occurs when the post-compaction payload remains at or above the trigger because protected head/tail messages, tool-pair integrity, fixed instructions, and tool schemas cannot be removed. Every subsequent model/tool iteration then compacts again while making little progress.

Safe response:

- Raise an abnormally low configured threshold toward the project default only after checking headroom.
- Keep a realistic requested output budget; do not confuse the model's maximum output capability with the per-request default.
- Treat current runtime values, resolver values, and vendor limits as separate evidence.
- A persisted config change may not affect an already-instantiated agent. State whether the change is **written**, **validated**, or **live**; a Python source patch requires a controlled service restart to become live in a long-running gateway.

## Boundary overrun reproducer

Degenerate sequence:

- one protected system message;
- every remaining message has `role="tool"`;
- `_align_boundary_forward(messages, 1)` advances to `len(messages)`;
- `_find_tail_cut_by_tokens()` initializes `cut_idx` to that value and may return `head_end + 1`;
- a downstream loop using `end=len(messages)+1` indexes `messages[len(messages)]`.

Minimal invariant:

```python
return min(max(cut_idx, head_end + 1), len(messages))
```

Regression coverage should assert both:

1. the computed tail boundary never exceeds `len(messages)`; and
2. end-to-end compression on an all-tool middle does not raise `IndexError`.

Do not weaken the test to “some exception occurred.” If summary generation is intentionally blocked, assert that any raised sentinel is not the boundary error and that the compressor never indexes past the list.

## Verification checklist

- focused regression passes;
- full ContextCompressor suite passes;
- `git diff --check` is clean;
- persisted threshold is read back from the config file or supported CLI output;
- runtime activation status is explicit;
- no arbitrary process killing: use a controlled service restart only when deployment is requested and the active conversation can tolerate disconnecting.

## Communication pitfall

Do not publish a causal conclusion while it is still an inference. In particular, verify the actual config before blaming maximum output reservation, and verify the resolver before blaming model metadata. Label hypotheses until the corresponding config/source/runtime evidence has been read.