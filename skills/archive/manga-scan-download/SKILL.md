---
name: manga-scan-download
description: Download latest manga scans (FR) from lelscans.net and send as PDF to Telegram.
category: media
---

# Manga Scan Download (FR)

Download manga chapters from lelscans.net, compile as PDF, and send via Telegram.

## Trigger
User wants the latest manga chapter (e.g. One Piece) in French.

## Steps

### 1. Find latest chapter
```
curl -sL -H "User-Agent: Mozilla/5.0" "https://lelscans.net/lecture-ligne-{manga}.php" | grep -oP '{manga}/[0-9]+' | sort -t/ -k2 -n | tail -1
```
Replace `{manga}` with the slug (e.g. `one-piece`).

### 2. Get page count and image URLs
URL pattern: `https://lelscans.net/scan-{manga}/{chapter}/{page}`
Image pattern: `https://lelscans.net/mangas/{manga}/{chapter}/{img_index}.jpg`

Page 1 is `00.jpg`, page 2 is `01.jpg`, etc. (zero-indexed images).

To find total pages, check navigation links on page 1:
```
curl -sL -H "User-Agent: Mozilla/5.0" "https://lelscans.net/scan-{manga}/{chapter}/1" | grep -oP '{chapter}/[0-9]+' | sort -u | sort -t/ -k2 -n
```

### 3. Download all pages
Use execute_code with subprocess to download all images to /tmp.

### 4. Compile to PDF
Use PIL or img2pdf to combine JPGs into a single PDF.

### 5. Send to Telegram
Use the send_message tool or Telegram Bot API to send the PDF document to the home channel.

## Pitfalls
- **MangaDex**: FR chapters often have externalUrl to MangaPlus with no pages hosted on MangaDex itself. Skip MangaDex for FR page downloads.
- **MangaPlus API**: Returns binary protobuf, not JSON. Do not try to parse it.
- **lelscans URL patterns**: Use `scan-{manga}/{chapter}/page` NOT `lecture-ligne-{manga}/{chapter}-page.php` (returns 404).
- **Image indexing**: First page image is `00.jpg` not `01.jpg`. Page N maps to image `{N-1:02d}.jpg`.
- **PDF size**: 16 manga pages is roughly 15-20MB. Telegram limit is 50MB for bots.

## Source
- Site: https://lelscans.net (dedicated One Piece FR scans)
- Telegram bot token and channel ID are in agent memory
