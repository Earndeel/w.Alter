# Gemini TTS Long Text Segmentation

## Problem
Gemini 3.1 Flash TTS API times out (60s HTTP timeout) on texts longer than ~1500 chars. The `text_to_speech` Hermes tool inherits this timeout.

## Solution: Segment + Concatenate

### Pattern
1. Split text at sentence boundaries into chunks of 400-500 chars
2. Call `text_to_speech` for each chunk → produces `/tmp/seg_N.mp3`
3. Create ffmpeg concat list
4. `ffmpeg -y -f concat -safe 0 -i list.txt -c copy output.mp3`

### Implementation (execute_code)
```python
import json, re
from hermes_tools import terminal

def segment_text(text, max_chars=450):
    """Split text at sentence boundaries."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) > max_chars and current:
            chunks.append(current.strip())
            current = s
        else:
            current = current + " " + s if current else s
    if current.strip():
        chunks.append(current.strip())
    return chunks

# Example usage:
text = "Your long podcast script here..."
chunks = segment_text(text)

# Generate each chunk
for i, chunk in enumerate(chunks):
    # Use text_to_speech tool (Hermes handles Gemini auth)
    # Save to /tmp/pod_seg_{i}.mp3
    pass

# Concatenate
with open('/tmp/concat_list.txt', 'w') as f:
    for i in range(len(chunks)):
        f.write(f"file '/tmp/pod_seg_{i}.mp3'\n")

terminal("ffmpeg -y -f concat -safe 0 -i /tmp/concat_list.txt -c copy /tmp/podcast_final.mp3")
```

### With Director's Notes (pre-prompt)
When using Gemini TTS with a style pre-prompt, the director's notes + transcript together count toward the char limit. Keep director's notes short (~200 chars) and only include them in the first segment, or send them as a separate preamble segment.

**Recommended structure for podcast generation:**
- Segment 0: Director's notes + intro text (~300 chars)
- Segments 1-N: Body text (~450 chars each)
- Last segment: Closing text

### Pitfalls
- Don't split mid-word or mid-tag (e.g., don't break `[slightly sarcastic]` across segments)
- Audio tags like `[excitedly]` or `[calm]` should stay with the sentence they modify
- ffmpeg concat requires same codec/sample rate across all segments (Gemini TTS always outputs 24kHz mono s16le PCM → converted to mp3/ogg by the tool, so this is consistent)
- For Telegram: OGG/Opus format is preferred for voice messages; MP3 for audio files
