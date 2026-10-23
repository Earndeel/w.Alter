---
name: kie-ai-api-direct
description: Call Kie.ai Claude/Gemini/GPT models directly via Python, bypassing Hermes runtime. Use when testing provider connectivity, debugging routing, or building one-shot API calls. Kie.ai exposes mixed protocol families; verify the exact endpoint contract, reasoning controls, and Hermes transport before integration. Hermes runtime calls must be verified against billing metadata to catch silent fallback.
---

## Endpoints

- `/claude/v1/messages` — Claude-family models
- `/v1/chat/completions` — GPT-family (OpenAI-compatible), where supported
- `/codex/v1/responses` — GPT-5.6/Codex Responses-style endpoint shown by the Kie.ai GPT-5.6 page; verify the page's current model, streaming, callback, and polling contract before implementation

For the GPT-5.6 thinking selector and Hermes integration verdict, see `references/gpt56-thinking-hermes-compatibility.md`.
For the reasoning field format (nested vs flat, smoke-tested), see `references/gpt56-reasoning-field-format.md`.
For reproducible evidence patterns, see `references/gpt56-hermes-verification.md`.
For the Hermes Desktop `/model` integration that exposes GPT 5.6 Sol as `low`, `medium`, `high`, `xhigh`, and `max`, see `references/hermes-desktop-sol-reasoning-picker.md`.
For Cloudflare 403 repairs across Claude and GPT Responses—including unified Desktop aliases and the two OpenAI client-construction paths—see `references/hermes-runtime-403-repair.md`.
When the UI shows the model but the provider dashboard shows no call, follow `references/hermes-provider-routing-vs-model-label.md` to distinguish a label change from real provider routing and to handle stale backends without blindly restarting a worker-heavy service.
For the full Desktop→gateway→agent→DB trace (including state.db verification queries, 403 patterns, and billing gaps), see `references/hermes-kie-harness-audit.md`.

## Video Generation (Grok Imagine)

Full API reference: `references/grok-imagine-video.md`

### Quick pricing
| Mode | Credits | Dollars |
|------|---------|---------|
| Text-to-video | 30 | $0.15 |
| Image-to-video | 30 | $0.15 |
| Credits rate | — | $0.005/credit |

**Image-to-video costs the same as text-to-video.** The advantage is quality control, not price.

### Image-to-video workflow (user's preferred method)
1. Plan keyframe + motion prompts (delegate to Fable 5 or DeepSeek V4)
2. Generate keyframe image via `image_generate`
3. Upload keyframe to public URL:
   ```bash
   curl -sF "reqtype=fileupload" \
        -F "fileToUpload=@/path/to/image.png" \
        https://catbox.moe/user/api.php
   ```
4. Submit to Kie image-to-video endpoint
5. Poll status: `GET /api/v1/jobs/recordInfo?taskId={taskId}` every 60-90s
6. States: `waiting` → `success` (with `generated_video_url`)

### Prompt style (corrected after ad QA — critical)
- **For a commercial ad, use an explicit timed multi-shot structure**: 4–6 distinct shots, hard cuts every 2–4 seconds, clear changes of framing, location, action, and visual information.
- Describe both **what is seen and how it moves**: handheld follow, push-in, lateral move, orbit, whip-pan, rack focus, walking action, object interaction. These are required when dynamism is part of the brief.
- Include an explicit **negative block**: no static talking head, no locked-off tripod, no single continuous shot, no idle standing, no slideshow, no generated subtitles, no generated logos, no watermark.
- Keep dialogue separate from the visual plan; never let a 15-second script become one uninterrupted monologue in one frame.
- The former “single flowing scene / no camera directions” rule applies only to a cinematic single-shot test, **not to paid advertising**.

Full API reference, pricing ($0.005/credit), and the ad-specific prompting rules are in `references/grok-imagine-video.md`.

Quick launch:
```python
resp = requests.post("https://api.kie.ai/api/v1/jobs/createTask",
    headers={"Authorization": f"Bearer {kie_key}"},
    json={
        "model": "grok-imagine/text-to-video",
        "duration": "10s",
        "resolution": "720p",
        "aspect": "16:9",
        "mode": "normal",
        "prompt": "A mint-green Lamborghini..."
    })
task_id = resp.json()["data"]["taskId"]
# Poll status: GET /api/v1/jobs/recordInfo?taskId={task_id}
```

## Common Patterns

```python
import requests, os

KIE_API_KEY = os.environ["KIE_API_KEY"]
curl -sS "${KIE_BASE}/credit" \
  -H "Authorization: Bearer ${KIE_API_KEY}"

## Grok Imagine Video 1.5 Preview (text-to-video)

Kie.ai exposes xAI's Grok Imagine Video through a task-based async API. Full details in
`references/grok-imagine-video.md`.

### API endpoint

```
POST https://api.kie.ai/api/v1/jobs/createTask
```

### Payload

```json
{
  "model": "grok-imagine/text-to-video",
  "input": {
    "prompt": "A cinematic description of what you want to see...",
    "mode": "normal",
    "aspectRatio": "16:9",
    "seconds": 10,
    "resolution": "720p"
  }
}
```

- `mode`: only `"normal"` is accepted. `"custom"` and `"fun"` were rejected as of 2026-07.
- `seconds`: video duration. 10s tested.
- `resolution`: `"720p"` tested. Higher resolutions may exist.
- `aspectRatio`: `"16:9"` tested.

### Polling

```
GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId={task_id}
```

Response fields: `state` (`"success"` / `"pending"` / `"queue"`), `output` (video URL), `credits` (cost).

### Pricing

- Kie credits: **$0.005/credit** (0.5 cent)
- 10s video = 30 credits = **$0.15**
- Cheaper than xAI direct ($0.05/sec = $0.50 for 10s).

### Prompt construction rules (critical)

Grok Imagine Video 1.5 is a **visual description model**, not a storyboard model.
These rules were learned from user corrections:
### Prompt construction rules (critical)

Grok Imagine Video 1.5 can produce a single visual beat when given a single-scene paragraph. For a **commercial advertisement**, the prompt must force an edited sequence:

1. **Use time-coded beats** — e.g. `0–2.5s`, `2.5–5s`, `5–8s`, `8–11.5s`, `11.5–15s` — with a hard cut between each beat.
2. **Change the visual information every 2–3 seconds**: exterior/interior, wide/medium/close, walking/action/demo/final address. Do not leave the subject standing in one place.
3. **Describe camera movement when needed**: handheld follow, push-in, lateral tracking, orbit, whip-pan, rack focus. “Dynamic” alone is too vague and must not be used as the only motion instruction.
4. **Use commercial grammar**: hook in the first two seconds, product/problem demonstration in the middle, clear human payoff and end beat. Leave the final frame clean for post-production logo, badge, and subtitles.
5. **Add a negative block**: no static talking head, no locked camera, no single continuous shot, no idle standing, no frozen background, no slideshow, no generated text, no subtitles, no logos, no watermark.
6. **If the model still collapses the sequence**, switch to image-to-video with a controlled keyframe, or generate separate short clips and assemble them in post-production. Do not waste another full 15-second credit on an unverified single-shot prompt.

**Bad** (single-shot prompt that fails an ad brief):
```
A farmer stands inside a greenhouse and speaks to camera for fifteen seconds. Natural UGC style, realistic lighting.
```

**Good** (commercial multi-shot prompt):
```
0–2.5s: hard cut to a wide exterior view of a farmer striding quickly toward a greenhouse as the camera moves backward with him; sunlight flashes across the roof panels, immediate energy and urgency.
2.5–5s: hard cut to a handheld medium shot as he pulls open the greenhouse entrance and gestures inside; the door, panels, ducts and crop rows enter the frame through active movement.
5–8s: hard cut to a close view of his hands demonstrating the installation, then a fast rack focus to his face as he turns and smiles; condensation and warm air visibly move around the system.
8–11.5s: hard cut to a side-following view as he walks through the greenhouse, points to the equipment and speaks with conviction; the background changes continuously.
11.5–15s: hard cut to a clean medium close-up outdoors, he stops, faces the viewer and delivers the final line with a confident gesture; leave uncluttered lower-third space for subtitles and the logo added later.
Negative: static talking head, locked-off tripod, single continuous shot, idle standing, frozen background, slideshow, generated text, subtitles, logos, watermark.
```

    "Content-Type": "application/json"
}

# Claude endpoint
resp = requests.post(
    "https://api.kie.ai/claude/v1/messages",
    headers={**headers, "anthropic-version": "2023-06-01"},
    json={"model": "claude-sonnet-4-20250514", "max_tokens": 1024, "messages": [{"role": "user", "content": "Hello"}]}
)

# GPT endpoint
resp = requests.post(
    "https://api.kie.ai/v1/chat/completions",
    headers=headers,
    json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}]}
)
```

## Pitfalls

- **Model discovery is protocol-prefix specific.** Do not assume the generic `https://api.kie.ai/v1/models` contract. For the Codex Responses family, probe `GET https://api.kie.ai/codex/v1/models` with Bearer auth; it may return model IDs without context-window, output-limit, or pricing metadata. Treat missing metadata separately from a missing model.
- **Hermes fallback risk.** When routing through Hermes runtime, verify billing metadata to confirm the call hit Kie.ai and not a silent fallback provider.
- **A model label is not provider evidence.** Verify the live session override includes both the provider identity and provider-native model ID; a friendly alias can still run through another provider. If backend code changed after service startup, account for Python/plugin module caching. Before restarting a dashboard service, inspect its cgroup because spawned workers may be terminated with it. See `references/hermes-provider-routing-vs-model-label.md`.
- **Presentation alias versus runtime provider.** The Desktop presentation group is `kie`; the Hermes runtime provider is `kie-gpt`. The gateway must normalize `kie → kie-gpt` before agent construction. A direct harness that instantiates `AIAgent(provider="kie")` bypasses that production normalization and can resolve the wrong API mode, endpoint, or credential—even when the real Desktop path is correct. Verify the normalizer with focused tests, then inspect the actual outbound URL and persisted `billing_provider`/`billing_base_url`. Do not infer a Desktop bug from a bypass harness.
- **Auth format.** Always `Bearer <key>`, regardless of endpoint path.
- **Codex Responses endpoint requires browser UA.** All calls to `https://api.kie.ai/codex/v1/*` must include `User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36` (any recent Chrome UA works). Without it, Cloudflare returns `HTTP 403: Your request was blocked`. Hermes v0.18.2 does NOT inject this for custom `codex_responses` providers.
- **Reasoning field MUST be nested, not flat.** Use `"reasoning": {"effort": "max"}` — never `"reasoning_effort": "max"`. The flat format is Chat Completions-native and causes a server 500 on the Responses endpoint. See `references/gpt56-reasoning-field-format.md`.
- **Responses streaming is not safely handled with a single `.json()` call.** Parse standard SSE events and tolerate line-delimited JSON when the compatibility endpoint emits it. Normalize both forms to Responses events and require a completed terminal event. Record the observed `Content-Type` in each contract probe instead of hard-coding “always SSE.”
- **Usage fields are compatibility-dependent.** `reasoning_tokens`, when present, is commonly nested at `usage.output_tokens_details.reasoning_tokens`. `input_tokens` may be populated—live Hermes persistence has recorded non-zero values—while reseller credit fields may still be absent. Preserve the raw usage object in probes and never convert missing pricing/credits into a claim of free usage.

## GPT-5.6 / Hermes verification discipline

For a GPT-5.6 Responses integration, separate three claims and verify each independently:

1. **Direct transport:** HTTP status, response `id`, response `model`, completion status, and tool-call shape.
2. **Reasoning semantics:** the request field being tested and the returned reasoning metadata/token usage. A response that echoes `reasoning.effort=max` but reports `reasoning_tokens=0` is not proof that maximum thinking was executed; report it as unconfirmed.
3. **Hermes routing:** capture the actual outbound URL/body, then inspect the temporary `state.db` session metadata (`billing_provider`, `billing_base_url`, `model`) to rule out fallback. A 403 before a provider response plus null billing metadata is an integration failure, not a successful agent test.

Use a temporary config/copy, cap the number of paid calls, and write a machine-readable report before returning a narrative. Preserve redacted request/response artifacts with absolute paths. The reproducible evidence checklist is in `references/gpt56-hermes-verification.md`.
