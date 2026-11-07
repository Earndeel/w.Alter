# Batch Media Retrieval for a Specific Chat

Full pipeline for extracting, filtering, and analyzing all media from a Beeper conversation.

## Problem

Beeper media directory (`~/Library/Application Support/BeeperTexts/media/local.beeper.com/`) has ~5500 files with no extensions and no chat association in filenames. You can't just `ls` and get what you need — you must cross-reference API metadata with local filesystem.

## Pipeline

### Step 1: Collect all attachment metadata via API

Paginate through `/v1/chats/{id}/messages` across ALL pages. For each message with attachments, extract:
- `attachments[].srcURL` → `file://` path, decode URL-encoding, get basename
- `attachments[].type` → `img`, `video`, `audio`
- `attachments[].isVoiceNote` → boolean
- `isSender` → boolean (to separate your media from theirs)
- `timestamp` → ISO 8601

Store as JSON for processing. Use `execute_code` with a pagination loop — terminal-only approaches hit output limits on large conversations (8000+ messages).

### Step 2: Cross-reference with Mac filesystem

Write filenames to a text file, SCP to Mac, then check existence + get sizes:

```bash
ssh lucasjouvencon@100.127.150.1 'bash -c "
BASE=\"/Users/lucasjouvencon/Library/Application Support/BeeperTexts/media/local.beeper.com\"
while IFS= read -r fname; do
    fpath=\"\$BASE/\$fname\"
    if [ -f \"\$fpath\" ]; then
        size=\$(stat -f%z \"\$fpath\" 2>/dev/null || echo 0)
        header=\$(xxd -l 8 -p \"\$fpath\" 2>/dev/null || echo \"unknown\")
        echo \"\$size|\$header|\$fname\"
    fi
done < /tmp/filenames.txt
"'
```

### Step 3: Filter stickers from real photos

| Size | Format | Verdict |
|------|--------|---------|
| < 50KB | GIF | Sticker/reaction — skip |
| 50-200KB | GIF | Animated sticker — skip unless specifically needed |
| exactly 43,655B | GIF | Instagram view-once placeholder — skip (all identical md5) |
| > 50KB | JPEG/PNG/WebP | Real photo — keep |
| any | OGG/MP4 | Audio/video — keep |

Detection via Python magic bytes (no `file` command needed on VPS):

```python
with open(path, "rb") as f:
    header = f.read(8)
if header[:3] == b'\xff\xd8\xff': ftype = "JPEG"
elif header[:8] == b'\x89PNG\r\n\x1a\n': ftype = "PNG"
elif header[:6] in (b'GIF87a', b'GIF89a'): ftype = "GIF"
elif header[:4] == b'RIFF': ftype = "WebP"
```

### Step 4: Copy filtered files from Mac to VPS

```bash
mkdir -p /tmp/bee_media/photos
scp lucasjouvencon@100.127.150.1:"$MAC_PATH/$fname" /tmp/bee_media/photos/
```

Sequential SCP over Tailscale is fast enough. Do NOT use `&` backgrounding in terminal — forbidden by Hermes.

### Step 5: Add proper extensions

Rename files by appending `.jpg`, `.png`, `.webp`, `.gif` based on magic bytes.

### Step 6: Analyze with vision model

**CRITICAL**: Shell argument length limit (~128KB). Base64-encoded images exceed this. Two approaches:

1. **Write payloads to JSON files**, then `curl -d @payload.json`
2. **Use `execute_code`** — orchestrates everything in Python, avoids shell limits entirely

```python
# In execute_code:
import json, base64, subprocess
payload = {
    "model": "google/gemini-2.5-flash",
    "messages": [{"role": "user", "content": [
        {"type": "text", "text": "Describe this image concisely."},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
    ]}],
    "max_tokens": 200
}
with open("/tmp/payload.json", "w") as f:
    json.dump(payload, f)
# Then: curl -d @/tmp/payload.json
```

## Typical Numbers

For an active chat with 8000+ messages:
- ~200-300 image attachments
- ~50-100 real photos (after sticker filtering)
- ~15-20 voice notes
- ~30-50 videos
- Total download: 10-50 MB
- Analysis time: 2-5 minutes (rate limited)

## Pitfalls

- **View-once placeholders**: All 43,655 bytes, identical md5 `5fcb582ab739fe57b5876242bbde4e30`. Detect and skip.
- **API pagination never ends**: `hasMore: true` is returned indefinitely. Cap at ~400 pages or when timestamps are old enough.
- **SCP tunnel**: Use Tailscale direct (`lucasjouvencon@100.127.150.1`), not localhost:2222 (autossh may not be running).
