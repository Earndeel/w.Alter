# TikTok Reference Video → Storyboard → Regeneration Pipeline

## Validated Workflow (May 2026)

### Step 1: Download
```bash
yt-dlp -f "mp4" --merge-output-format mp4 --restrict-filenames --no-mtime "<tiktok_url>"
```
All 4 TikTok formats tested and downloaded successfully.

### Step 2: Archive to Drive
Use `google-api-python-client` with the `w.alter` folder (`1Uj8ESyV92yiMonQ1Ti5qZXAe_jmabwC2`) for shared references.

### Step 3: Analyze with Gemini → Scene Breakdown
**Model**: `google/gemini-2.5-flash` on OpenRouter (base64 if video <5MB)
**Prompt**: "Analyse cette video avec precision sur le temps, decoupe en scenes de 3-15s max. Pour chaque scene donne: timestamp depart/fin, description visuelle detaillee (personnage, decor, mouvement), transitions, et un prompt en anglais pour un modele video IA."

Result format: 4 scenes with timestamps, descriptions, and English AI prompts for regeneration.

### Step 4: Storyboard with GPT Image 2
2 keyframes per scene (before/after), vertical 1080×1920, using Atlas Cloud.
- Prompt format: "Vertical 9:16, photorealistic UGC style. [Scene description]. TikTok social media aesthetic."
- Submit all frames in parallel, poll together.

### Step 5: Generate Clips with Seedance 2
Use each storyboard keyframe as image reference via Kie.ai `seedance2` model.
- Each clip: 4-8 seconds per AI generation limit
- Postprod: stitch clips, add text overlays ("Day 1", "Day 30", etc.), match audio

## Known Working Example: Red Light Therapy Hair Growth Cap
4 scenes: Day 1 → Day 30 → Day 90 → Day 120
Original: 12s TikTok, regenerated as 4×3s clips
Cost: ~$0.005 for Gemini 2.5 Flash analysis, ~$0.08 for 8 GPT Image 2 storyboards
