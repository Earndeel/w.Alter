# Beeper Media Access Pipeline

The Beeper API does NOT serve media files — only metadata. But SSH access to the Mac provides direct filesystem access.

## Media directory

```
~/Library/Application Support/BeeperTexts/media/
├── beeper.com/
├── gitter.im/
└── local.beeper.com/   ← most media lives here (~5000+ files, no extensions)
```

Files have NO extensions. Use `file -b --mime-type` to detect type. If `file` is not installed on VPS, use Python magic bytes:
```python
with open(path, 'rb') as f:
    h = f.read(8)
    if h[:3] == b'\xff\xd8\xff': mime = 'image/jpeg'
    elif h[:8] == b'\x89PNG\r\n\x1a\n': mime = 'image/png'
    elif h[:6] in (b'GIF87a', b'GIF89a'): mime = 'image/gif'
    elif h[:4] == b'RIFF': mime = 'image/webp'
```

### View-once / ephemeral photos (Instagram)
Instagram "view-once" photos (*"This photo can only be replayed once"*) are stored as **identical placeholder GIFs** — always exactly 43,655 bytes, GIF89a header. All copies share the same md5 hash. The actual image data is NOT cached on disk. These are unrecoverable after viewing.

Regular (non-ephemeral) images and stickers are stored normally and can be SCP'd. For batch retrieval of a specific chat's images, see `references/batch-media-retrieval.md`.

## Step 1: Copy file from Mac to VPS

```bash
# Via scp through Tailscale
scp lucasjouvencon@100.127.150.1:"/Users/lucasjouvencon/Library/Application\ Support/BeeperTexts/media/local.beeper.com/<filename>" /tmp/beeper-media/
```

## Step 2: Detect file type

```bash
file -b --mime-type /tmp/beeper-media/<filename>
# → image/jpeg, audio/ogg, image/png, etc.
```

## Step 3a: Image analysis (free, ~2s)

Prefer OpenRouter with Gemini 2.5 Flash for guaranteed reliability. The built-in `vision_analyze` tool may work depending on session model — try it first if convenient, fall back to OpenRouter if it fails.

```bash
OPENROUTER_KEY=$(vault get openrouter/api_key)
IMAGE_B64=$(base64 -w0 /tmp/beeper-media/image.jpg)

curl -s "https://openrouter.ai/api/v1/chat/completions" \
  -H "Authorization: Bearer $OPENROUTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemini-2.5-flash",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "Describe this image."},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,'"$IMAGE_B64"'"}}
      ]
    }],
    "max_tokens": 300
  }' | python3 -c "import json,sys; print(json.load(sys.stdin)['choices'][0]['message']['content'])"
```

## Step 3b: Audio transcription (free, ~1s)

Use Groq Whisper large-v3-turbo — free, fast, supports French.

```bash
GROQ_KEY=$(vault get groq/api_key)

curl -s -X POST "https://api.groq.com/openai/v1/audio/transcriptions" \
  -H "Authorization: Bearer $GROQ_KEY" \
  -F "file=@/tmp/beeper-media/audio.ogg" \
  -F "model=whisper-large-v3-turbo" \
  -F "language=fr" | python3 -c "import json,sys; print(json.load(sys.stdin)['text'])"
```

Works with `.ogg` (Beeper voice notes), `.m4a`, `.mp3`, `.wav`, `.webm`.

## Full media scan

```bash
ssh lucasjouvencon@100.127.150.1 '
find ~/Library/Application\ Support/BeeperTexts/media/ -type f | while read f; do
  mime=$(file -b --mime-type "$f" 2>/dev/null)
  if echo "$mime" | grep -qE "image/|audio/"; then
    echo "$f|$mime"
  fi
done | head -20
'
```

## Cost summary

| Media type | Model | Provider | Cost | Speed |
|-----------|-------|----------|------|-------|
| Images | Gemini 2.5 Flash | OpenRouter | Free | ~2s |
| Audio | Whisper Large V3 Turbo | Groq | Free | ~1s |
