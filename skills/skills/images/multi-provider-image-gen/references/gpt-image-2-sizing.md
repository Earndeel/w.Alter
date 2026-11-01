# GPT Image 2 — Atlas Cloud Sizing Guide

## CRITICAL: Dimensions must be multiples of 16

Both width AND height must be divisible by 16. This is an upstream GPT Image 2 requirement.

### Valid sizes

| Aspect | Size | Use Case |
|---|---|---|
| 9:16 vertical | `1024x1792` | TikTok, IG Reels, Stories |
| 16:9 landscape | `1792x1024` | YouTube thumbnails |
| 1:1 square | `1024x1024` | Product cards |
| 1:1 square | `2048x2048` | Hi-res products |

### Will error ("size must be multiples of 16")

- `1080x1920` — 1080/16 = 67.5 ✗
- `1440x2560` — works for ERNIE only
- `720x1280` — 720/16 = 45 ✗

### ERNIE sizing (no 16-multiple constraint)

ERNIE accepts any size. Standard vertical: `1440x2560`.

## Download method

**GPT Image 2**: Always `enable_base64_output: true`. URL output expires within seconds (NoSuchKey from Aliyun OSS).

**ERNIE**: URL-based output, download immediately after poll.
