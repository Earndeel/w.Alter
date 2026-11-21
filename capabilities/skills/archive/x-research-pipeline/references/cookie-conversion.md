# Cookie Conversion: X JSON → Netscape (for yt-dlp)

yt-dlp requires Netscape-format cookies. Convert from Playwright JSON export:

```python
import json

with open("/tmp/x_cookies.json") as f:
    cookies = json.load(f)

with open("/tmp/x_cookies_netscape.txt", "w") as f:
    f.write("# Netscape HTTP Cookie File\n")
    for c in cookies:
        domain = c.get("domain", ".x.com")
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path", "/")
        secure = "TRUE" if c.get("secure", True) else "FALSE"
        expires = str(int(c.get("expires", 0)))
        f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{c['name']}\t{c['value']}\n")
```

Usage: `yt-dlp --cookies /tmp/x_cookies_netscape.txt <url>`

## Pitfall: Post ID vs Thumbnail ID

X video thumbnails use URLs like:
`pbs.twimg.com/amplify_video_thumb/<THUMBNAIL_ID>/img/...`

This is NOT the post ID. The actual post URL is:
`x.com/<handle>/status/<POST_ID>`

yt-dlp needs the POST_ID, not the THUMBNAIL_ID. Extract from the `url` field of scraped posts.
