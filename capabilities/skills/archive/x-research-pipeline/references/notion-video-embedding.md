# Embedding X Videos in Notion

## ⚠️ Cost Warning

R2 + Cloudflare Worker approach WORKS but **Lucas ne veut PAS payer pour ça**. 
The Worker `koda-media` and R2 files were deleted after the session.
Use **bookmarks** (free) or **YouTube/Loom** (free, inline) instead.

## What works (free)

### Bookmarks (recommended)
Rich preview cards with title + description. Click to open in X.
```python
{"object": "block", "type": "bookmark", "bookmark": {
    "url": "https://x.com/handle/status/ID",
    "caption": [rich("Title (N likes)")]
}}
```
- ✅ Gratuit
- ✅ Rich preview (titre, description, favicon)
- ❌ Pas de lecture inline (clic requis)

### YouTube/Loom (not tested)
Upload videos → embed Notion video blocks. Free tier available.
- ✅ Gratuit
- ✅ Lecture inline
- ❌ Re-upload manuel nécessaire

## What works but costs money

### R2 + Cloudflare Worker
```
yt-dlp → R2 bucket → Worker proxy → Notion video block
```
- ✅ Lecture inline dans Notion
- ❌ Coût Cloudflare (R2 storage + Worker requests)
- ❌ Worker doit être créé/supprimé à chaque session

### Pipeline (if ever needed)
1. `yt-dlp --cookies /tmp/x_cookies_netscape.txt -f "best[height<=480]/best" -o "output.mp4" "<url>"`
2. Upload to R2: `curl -X PUT "https://api.cloudflare.com/client/v4/accounts/<ACCOUNT>/r2/buckets/<BUCKET>/objects/<key>" -H "Authorization: Bearer <TOKEN>" --data-binary "@file.mp4"`
3. Deploy Worker (see r2-setup-and-video-pipeline skill)
4. Notion video block: `{"type": "video", "video": {"type": "external", "external": {"url": "<worker-url>/<key>.mp4"}}}`

## What does NOT work

| Méthode | Résultat |
|---|---|
| `embed` block avec URL X | "error loading" — X bloque l'intégration |
| `image` block avec thumbnail | Image statique, pas de vidéo |
| R2 direct (`pub-*.r2.dev`) | 401 Unauthorized — bucket pas public par défaut |
| Notion `video` block avec URL X | Ne se charge pas — X requiert auth |

## Images from X

Images from X (`pbs.twimg.com/media/...`) work perfectly as Notion `image` blocks with external URLs. Notion fetches and caches them.
```python
{"object": "block", "type": "image", "image": {"type": "external", "external": {"url": "https://pbs.twimg.com/media/..."}}}
```

## Pitfalls

- **yt-dlp "No video found"** → vérifier que l'URL est bien un post avec vidéo (pas une image). Les posts avec `amplify_video_thumb` dans les URLs d'images contiennent des vidéos.
- **Post ID vs Thumbnail ID** → `amplify_video_thumb/<ID>/img/` est le thumbnail ID, PAS le post ID. Le bon format: `x.com/<handle>/status/<post_id>`.
- **Notion limit: 100 blocks** par appel API → paginer si plus de contenu.
- **yt-dlp cookies** → format Netscape requis. Voir `references/cookie-conversion.md`.
