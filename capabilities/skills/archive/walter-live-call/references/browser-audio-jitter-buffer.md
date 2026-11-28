# Browser Audio Jitter Buffer (2026-05-26)

## Problem
Gemini Live sends audio chunks at irregular intervals via WebSocket. Without buffering, the AudioWorklet playback processor plays each chunk immediately on arrival. When chunks arrive late or in bursts, this creates audible gaps and crackling.

## Solution: Ring Buffer with Pre-buffering
The playback worklet (`playback.worklet.js`) accumulates audio in a ring buffer before starting playback. At 24kHz sample rate:

- **Pre-buffer threshold**: 4800 samples = 200ms — wait until this much audio is buffered before starting playback
- **Ring buffer size**: 16384 samples = ~680ms headroom
- **Underrun handling**: play what's available, fill rest with silence; after 30 consecutive underruns (~160ms), return to pre-buffering phase
- **Interrupt**: flush entire buffer, reset to pre-buffer phase

### Key design decisions
1. **Pre-buffer adds ~200ms initial latency** — acceptable for conversational voice, eliminates jitter
2. **Ring buffer with power-of-2 size** — fast modulo via bitwise AND (though JS doesn't optimize this automatically, it's cleaner)
3. **Silence fill on underrun** — avoids crackling from stale buffer data
4. **30-underrun fallback to pre-buffer** — prevents sustained crackling during long pauses; Gemini sends audio in bursts, so brief underruns are normal

## Capture buffer sizing
`capture.worklet.js` bufferSize determines how many samples are accumulated before sending a WebSocket message:

| bufferSize | Duration (at 16kHz) | Messages/sec | Trade-off |
|------------|---------------------|-------------|-----------|
| 512 | 32ms | ~31 | Too many WS messages, high overhead |
| **1024** | **64ms** | **~16** | **Sweet spot — low overhead, imperceptible latency** |
| 2048 | 128ms | ~8 | Noticeable input latency |

## Cache-busting
Browsers aggressively cache AudioWorklet modules loaded via `addModule()`. Always append a timestamp:
```javascript
await this.audioContext.audioWorklet.addModule(`/static/audio-processors/capture.worklet.js?v=${Date.now()}`);
```

Also cache-bust `<script>` tags in `index.html` on any JS change:
```html
<script src="/static/app.js?v=20260526" defer></script>
```

## Voice inconsistency trap
`geminilive.js` constructor sets `this.voiceName = "Algenib"`. If this doesn't match the `VOICE` constant in `app.js`, the constructor default wins because it runs before `setVoice()` is called. Always keep them in sync.

## Files
- `/root/.hermes/voice-call/static/audio-processors/playback.worklet.js` — jitter buffer implementation
- `/root/.hermes/voice-call/static/audio-processors/capture.worklet.js` — capture buffer
- `/root/.hermes/voice-call/static/mediaUtils.js` — AudioStreamer + AudioPlayer classes
- `/root/.hermes/voice-call/static/geminilive.js` — GeminiLiveAPI client (voice default)
- `/root/.hermes/voice-call/static/app.js` — main app (VOICE constant)
- `/root/.hermes/voice-call/static/index.html` — script tags (cache-bust here)
