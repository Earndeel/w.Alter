# Word-synchronised highlight subtitles

Use this reference when a finished video needs burned-in subtitles where the currently spoken word changes colour. This is deterministic post-production: derive timing from the delivered audio, build ASS events, render a separate MP4, and prove that the audio stayed unchanged.

## Release contract

A valid result has all of the following:

- timing comes from word-level ASR on the actual delivered media;
- the active word alone uses the highlight colour during its spoken interval;
- surrounding words stay in the base colour;
- chunks contain enough context to make highlighting meaningful;
- no subtitle block exceeds two lines or the safe horizontal width;
- captions disappear during non-speech gaps;
- audio is copied unchanged unless the brief explicitly requests audio edits;
- decoded frames prove legibility and synchronization at representative words.

## Build the ASS file

The packaged helper consumes faster-whisper-style JSON:

```json
{
  "segments": [
    {
      "words": [
        {"start": 0.62, "end": 1.16, "word": " Les"}
      ]
    }
  ]
}
```

For concatenated clips, add each transcript with its master-timeline offset:

```bash
python3 scripts/build_word_highlight_ass.py \
  --segment /tmp/clip_a_words.json@0 \
  --segment /tmp/clip_b_words.json@10 \
  --font-file /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf \
  --font-name "DejaVu Sans" \
  --output /tmp/captions.ass
```

The script merges French clitics split by ASR (`d` + `'agriculteurs`, `l` + `'air`), groups sentence words into contextual chunks, measures rendered text with Pillow, and inserts explicit `\N` breaks only when needed. Its default 720×1280 preset uses 48 px bold text, a 620 px line-width ceiling, at most five words per chunk, two lines maximum, a 170 px bottom margin, white base text, and a yellow active word.

## ASS colour and layout details

ASS colours are `&HAABBGGRR&`, not RGB. Examples:

- white: `&H00FFFFFF&`;
- yellow/gold RGB `#FFD54A`: `&H004AD5FF&`;
- opaque black outline: `&H00000000&`.

Use alignment `2` for bottom-centred captions. For 720×1280 social video, keep explicit left/right margins and a bottom margin large enough to avoid platform controls. Do not animate scale on each active word unless tested: re-centering can make the whole line jitter.

## Render

Burn the subtitles into a new copy and preserve audio explicitly:

```bash
ffmpeg -y -i source.mp4 \
  -vf "subtitles=/tmp/captions.ass:fontsdir=/path/to/fonts" \
  -map 0:v:0 -map 0:a:0 \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
  -c:a copy -movflags +faststart output_karaoke.mp4
```

Keep the unsubtitled master. Burned-in captions are intentionally irreversible.

## Verification

1. Run full decode and `ffprobe` on the rendered MP4.
2. Extract frames inside at least six known word intervals, including:
   - a short common word;
   - the longest word;
   - a proper noun/acronym;
   - an accented word;
   - a French apostrophe/clitic;
   - the final word.
3. Build a labeled contact sheet and verify that the expected word alone is highlighted.
4. Build a 1 fps full-timeline contact sheet to catch overflow, position drift, and captions persisting into silence.
5. Compare decoded audio MD5 values:

```bash
ffmpeg -v error -i source.mp4 -map 0:a:0 -f md5 -
ffmpeg -v error -i output_karaoke.mp4 -map 0:a:0 -f md5 -
```

Matching MD5 values prove that subtitle rendering did not alter the decoded audio.

## Pitfalls

- **Single-word pseudo-highlights:** a chunk containing only one word technically changes colour but gives no contextual highlight. Prefer balanced 4–5-word groups, then reduce only when pixel-width measurement requires it.
- **Three-line overflow:** word-count limits alone are insufficient in French; long words such as `gratuitement` or `d'agriculteurs` require real font measurement.
- **Concatenation offsets:** a transcript for clip B remains relative to clip B. Add the exact master offset before generating ASS events.
- **Split apostrophes:** ASR may output `d` and `'agriculteurs` separately. Merge them before chunking or the highlight flashes twice on one spoken word.
- **Preview seeking:** input-side `-ss` may reset timestamps before the subtitle filter. Render the full copy first, or use output-side seeking so ASS timing is evaluated on the original timeline.
- **Audio mutation:** subtitle work is video-only. Map audio explicitly and prefer `-c:a copy`; verify decoded MD5 afterward.
- **ASS colour inversion:** entering RGB directly produces the wrong highlight because ASS uses BGR order.
