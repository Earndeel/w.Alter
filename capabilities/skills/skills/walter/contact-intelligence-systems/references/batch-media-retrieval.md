# Beeper Batch Media Retrieval

Complete pipeline for extracting, filtering, and analyzing media from a specific Beeper chat.

## Step 1: Collect filenames from API

Paginate through `/v1/chats/{id}/messages`, collect all `attachments[].srcURL` values. Each srcURL is a `file://` URL with the Mac filesystem path.

```python
import json, subprocess, urllib.parse, os

TOKEN = subprocess.check_output("vault get beeper/token", shell=True).decode().strip()
API = "http://100.127.150.1:23373"

all_media = []
cursor = None
while True:
    url = f"{API}/v1/chats/{chat_id}/messages?limit=50"
    if cursor:
        url += f"&cursor={cursor}"
    result = subprocess.check_output(f'curl -s "{url}" -H "Authorization: Bearer {TOKEN}"', shell=True).decode()
    data = json.loads(result)
    items = data.get("items", [])
    for m in items:
        for a in m.get("attachments", []):
            src = urllib.parse.unquote(a.get("srcURL", "")).replace("file://", "")
            if src:
                all_media.append({
                    "ts": m.get("timestamp", ""),
                    "sender": "MOI" if m.get("isSender") else "ELLE",
                    "type": a.get("type", ""),
                    "path": src,
                    "filename": os.path.basename(src)
                })
    if not items or not data.get("hasMore"):
        break
    cursor = items[-1].get("sortKey")
```

## Step 2: Check which files exist on Mac + get sizes

```bash
# Write filenames to file, SCP to Mac, check existence
scp /tmp/filenames.txt lucasjouvencon@100.127.150.1:/tmp/filenames.txt
ssh lucasjouvencon@100.127.150.1 'bash -c "
BASE=\"/Users/lucasjouvencon/Library/Application Support/BeeperTexts/media/local.beeper.com\"
while IFS= read -r fname; do
    fpath=\"\$BASE/\$fname\"
    if [ -f \"\$fpath\" ]; then
        size=\$(stat -f%z \"\$fpath\" 2>/dev/null || echo 0)
        header=\$(xxd -l 8 -p \"\$fpath\" 2>/dev/null || echo unknown)
        echo \"\$size|\$header|\$fname\"
    fi
done < /tmp/filenames.txt
"' > /tmp/mac_file_info.txt
```

## Step 3: Filter stickers from real photos

```python
# Filter criteria:
# - JPEG/PNG/WebP > 50KB → real photo (KEEP)
# - GIF < 50KB → sticker/reaction (SKIP)
# - GIF > 50KB but same size as others → view-once placeholder (SKIP)
# - Large GIF (1MB+) → animated sticker (SKIP unless needed)

real_images = []
for entry in file_info:
    size, header, fname = parse(entry)
    if size < 50000: continue  # stickers
    if header.startswith("47494638"): continue  # GIF — skip all GIFs for real photos
    if header.startswith("ffd8ff"): ftype = "JPEG"  # keep
    elif header.startswith("89504e47"): ftype = "PNG"  # keep
    elif header.startswith("52494646"): ftype = "WebP"  # keep
    else: continue
    real_images.append({"filename": fname, "size": size, "type": ftype})
```

## Step 4: Batch SCP from Mac to VPS

```bash
# Copy all at once
scp lucasjouvencon@100.127.150.1:"/Users/lucasjouvencon/Library/Application Support/BeeperTexts/media/local.beeper.com/{filename}" /tmp/photos/
```

## Step 5: Add proper extensions via magic bytes

```python
import os
for fname in os.listdir("/tmp/photos/"):
    path = os.path.join("/tmp/photos/", fname)
    with open(path, "rb") as f:
        header = f.read(8)
    ext = ""
    if header[:3] == b'\xff\xd8\xff': ext = ".jpg"
    elif header[:8] == b'\x89PNG\r\n\x1a\n': ext = ".png"
    elif header[:4] == b'RIFF': ext = ".webp"
    if ext:
        os.rename(path, path + ext)
```

## Step 6: Analyze with OpenRouter vision

```python
# CRITICAL: Write payload to JSON file, don't pass inline (shell arg limit)
import json, base64, subprocess

OPENROUTER_KEY = subprocess.check_output("vault get openrouter/api_key", shell=True).decode().strip()

for photo in photos:
    with open(photo["path"], "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    
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
    
    result = subprocess.check_output(
        f'curl -s "https://openrouter.ai/api/v1/chat/completions" '
        f'-H "Authorization: Bearer {OPENROUTER_KEY}" '
        f'-H "Content-Type: application/json" '
        f'-d @/tmp/payload.json',
        shell=True, timeout=30
    ).decode()
    
    desc = json.loads(result)["choices"][0]["message"]["content"]
```

## Pitfalls

- **Shell arg length**: Base64 images are ~100KB+ — always write to file, use `curl -d @file`
- **`file` command missing**: Use Python magic bytes on VPS
- **View-once placeholders**: All exactly 43,655 bytes, same MD5. Skip them.
- **SCP via Tailscale**: Use `lucasjouvencon@100.127.150.1` directly, not localhost:2222
- **GIF detection**: GIFs can be stickers OR animated content. For real photos, filter out ALL GIFs.
