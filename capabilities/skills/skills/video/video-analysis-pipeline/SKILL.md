---
name: video-analysis-pipeline
category: ad-pipeline
description: "Complete workflow: OpenRouter direct video upload analysis -- model routing, system prompt structure, Flask blueprint endpoint, and UI analysis tab. Also covers: openrouter video input."
---

## When to Use

- Analyzing product/cosmetic videos for ad pipeline quality scoring
- Need to route video through OpenRouter multimodal models for structured analysis
- Building video analysis dashboards with Flask

## Pitfalls

- OpenRouter free tier hits 429 rate limits ~20-30% during peak hours — retry with exponential backoff
- System prompt MUST be separate from user content in the API call — don't embed instructions in the user message array
- Videos >150MB need ffmpeg compression before base64 encoding
- API calls take 90-130 seconds per video — don't set tight timeouts
- `card_id` is not a primary key — multiple analyses possible per card (INSERT OR UPDATE pattern)

# Video Analysis Pipeline

Complete workflow for analyzing product videos using OpenRouter multimodal models via **direct video upload** (base64 encoded MP4). No frame extraction needed.

## Architecture

```
Local MP4 → Base64 encode → OpenRouter API (system prompt + video) → JSON Analysis → Pipeline DB → Dashboard UI
```

## Current Stack (as of 2026-04-06)

### Project Structure
```
/root/projects/ad-video-pipeline/
├── app/                          # Flask application package
│   ├── __init__.py               # App factory, registers blueprints
│   ├── config.py                 # Centralized paths (DB_PATH, VIDEO_DIR, PROMPT_PATH)
│   ├── database.py               # DB helper (get_db, extract_score)
│   ├── main.py                   # Main blueprint: cards, stats, analysis GET, video streaming
│   ├── analysis.py               # Analysis blueprint: /api/analyze POST, /api/preprompt GET/PUT
│   └── kling.py                  # Kling blueprint: payload generation, submission, status
├── modules/
│   └── video_analyzer_v3.py      # Core analysis engine (OpenRouter direct video call)
├── prompts/
│   └── video_analysis_prompt.md  # System prompt template (editable via dashboard)
├── run.py                        # Flask entry point: python3 run.py → port 5001
├── pipeline.db                   # SQLite database
└── templates/
    └── index.html                # Dashboard UI (ES5 vanilla JS only)
```

### Dashboard URL
- `http://100.91.35.121:5001` or `http://localhost:5001`

## OpenRouter Direct Video Upload

### Model
- **Primary**: `qwen/qwen3.6-plus:free` — free, supports native video input
- **Configured in**: `video_analyzer_v3.py`, line 20: `MODEL = 'qwen/qwen3.6-plus:free'`

### Payload Structure (CRITICAL)
```python
messages = [
    {
        "role": "system",
        "content": prompt_text  # Full video_analysis_prompt.md with variables substituted
    },
    {
        "role": "user",
        "content": [
            {"type": "text", "text": f"Analyse de video cosmetique: {card_name} | Duree: {duration:.1f}s"},
            {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{video_b64}"}}
        ]
    }
]
payload = {"model": MODEL, "messages": messages, "max_tokens": 8000}
```

**Key finding**: System prompt MUST be separate from user content. Don't embed instructions in the user message array.

### Video Encoding Details
- Files are base64 encoded directly: `base64.b64encode(open(path, 'rb').read()).decode()`
- Max payload: 150 MB (enforced in analyzer)
- Videos >150MB: auto-compressed with `ffmpeg -vf scale=720:1280 -crf 28`
- Typical sizes: 1-6 MB videos → 1.5-8 MB base64 payloads
- Call takes 90-130 seconds for a ~1-5 MB video

### API Response Structure
```json
{
    "ok": true,
    "chars": 12521,
    "time": 109.0,
    "usage": {
        "prompt_tokens": 7720,
        "completion_tokens": 4649,
        "total_tokens": 12369,
        "cost": 0,
        "completion_tokens_details": {"reasoning_tokens": 1455}
    }
}
```

## Flask Blueprint Endpoints

### Analysis Blueprint (`app/analysis.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/analyze/<card_id>` | POST | Triggers analysis, returns `{"ok", "chars", "time", "usage"}` |
| `/api/preprompt` | GET | Returns current prompt content + path |
| `/api/preprompt` | PUT | Saves updated prompt content |

**Analysis endpoint flow**:
1. Verify video exists and is `download_status='completed'`
2. Load current preprompt from `PROMPT_PATH`
3. Insert `modules/` into `sys.path`, `reload(video_analyzer_v3)`
4. Call `mod.analyze_video(card_id, prompt_text)` → returns `(analysis_text, usage)`
5. Call `mod.save_analysis(card_id, analysis_text, usage)` → saves to DB
6. Return `{"ok": True, "chars": N, "time": seconds, "usage": {...}}`

### Main Blueprint (`app/main.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve dashboard template |
| `/api/cards` | GET | Return all cards with analysis metadata |
| `/api/analysis/<card_id>` | GET | Return full analysis_text + card details |
| `/api/stats` | GET | Return aggregate statistics |
| `/api/video/<card_id>` | GET | Stream video with Range header support (206 partial) |

## Dashboard UI Analysis Tab

### Location
The "Analyser" button is in the **📝 Analyse tab** of the detail view (not in the topbar).

### Workflow
1. Click a card in the grid → opens detail view
2. 📝 Analyse tab shows automatically (first tab)
3. If not analyzed: shows empty state + "🔍 Analyser la video" button
4. If already analyzed: shows "🔄 Relancer l'analyse" button + loads existing analysis
5. Click Analyser → button disables, status shows "Appel API en cours..."
6. On success: reloads cards data, fetches analysis text, displays it in-place
7. On error: shows error message with "🔄 Reessayer" button
8. Tab pill updates to show character count: `📝 Analyse (12521 chars)`

### Key JS Functions
- `runAnalysis()` — POST to `/api/analyze/<id>`, updates UI in-place
- `buildTabs(card, ana, kvu)` — builds all 4 tabs (Analyse, Comments, Kling, JSON)
- `updateAnalysisStatus()` — updates tab pill with char count
- `loadCards()` — refreshes card data from server

## Simple Web App / Cloudflare Variant

This pipeline also works well as a lightweight public web app on Cloudflare when the only goal is:
- upload an input video
- translate it into a detailed JSON analysis
- render the result in a clean design
- keep configuration simple for the user

### Reusable product pattern
- Keep the frontend static and minimal
- Use a single analysis endpoint on the backend/worker
- Make provider settings optional in the UI
- Default to a working model/config so the app works immediately
- Expose a separate test-connection endpoint for advanced custom providers

### Important implementation finding
For this class of app, the safest UX is:
- default provider prefilled and usable out of the box
- empty Settings state must not block analysis
- custom provider support stays optional
- test-connection must accept empty bodies and custom configs cleanly

### Suggested default behavior
- Default model: Gemini 3 Flash via AI Studio
- OpenRouter stays available as an advanced option
- If the Settings panel is empty, the app should still analyze videos successfully

### Deployment target
- Best fit: Cloudflare Pages for the UI
- Use a Worker only if you need API routes, auth, or file handling
- Keep the public surface simple so the app is easy to share and operate

## Database Schema

### video_analysis table
```sql
CREATE TABLE video_analysis (
    card_id INTEGER NOT NULL,
    analysis_text TEXT,
    kling_status TEXT DEFAULT 'none',
    kling_request_id TEXT,
    kling_result TEXT,           -- JSON array of result URLs
    model_used TEXT,             -- 'qwen/qwen3.6-plus:free'
    tokens_prompt INTEGER,
    tokens_completion INTEGER,
    frames_analyzed INTEGER DEFAULT 0,
    analyzed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Note**: `card_id` is indexed but not a primary key (multiple analyses possible per card — `save_analysis` does INSERT OR UPDATE pattern).

## File Locations

| Component | Path |
|-----------|------|
| Analyzer | `/root/projects/ad-video-pipeline/modules/video_analyzer_v3.py` |
| Prompt | `/root/projects/ad-video-pipeline/prompts/video_analysis_prompt.md` |
| Flask app | `/root/projects/ad-video-pipeline/app/` |
| Entry point | `/root/projects/ad-video-pipeline/run.py` |
| Dashboard | `/root/projects/ad-video-pipeline/templates/index.html` |
| Database | `/root/projects/ad-video-pipeline/pipeline.db` |
| Videos | `/root/projects/ad-video-pipeline/output/videos/` |

## Common Issues & Solutions

### 1. HTTP 502 from OpenRouter
- Cause: OpenRouter upstream service temporarily down
- Solution: Wait and retry — the retry loop handles 5 attempts

### 2. HTTP 429 Rate Limited
- Cause: Free tier rate limit (common during peak hours)
- Solution: Retry loop uses exponential backoff: 15s * attempt number, max 5 retries
- Cards with 429 errors show `ERROR: Rate limit 429` in `analysis_text` and can be re-analyzed

### 3. Flask App Not Responding
- Old `dashboard.py` still running after refactor
- Fix: Kill old process, start with `python3 run.py`
- Check: `curl -s http://localhost:5001/api/stats`

### 4. Empty analysis_text or 32 chars response
- Usually means HTTP 502/429 error was caught and saved
- Check DB: `SELECT analysis_text FROM video_analysis WHERE card_id = X`
- Re-trigger via dashboard: click Relancer in Analyse tab

### 5. Prompt Template Variable Substitution
- The `load_prompt_template()` function tries to substitute `{card_name}`, `{product_name}`, etc.
- If substitution fails (KeyError), it falls back to raw template — this is acceptable
- The video_analysis_prompt.md uses generic instructions, not card-specific variables

## Real-World Performance
- **Per video**: 90-130 seconds (encoding + API call + save)
- **Video sizes**: 1-6 MB typical, max file 31 MB (card #11)
- **Analysis output**: 3,000-15,000 chars depending on video length
- **Token usage**: ~7,000-12,000 prompt, ~3,000-9,000 completion
- **Cost**: $0.00 on free tier
- **429 rate limits**: ~20-30% of attempts during peak hours on free tier
- **Batch of 15 videos**: ~25-40 minutes with retry backoffs

## Also covers (merged 2026-11-01)

These procedures were separate skills; their full original text is kept here, unchanged.

- **openrouter-video-input** — Sending video to models through OpenRouter's native video input: model catalogue, payload formats and the R2 upload workflow for large files.
  Read `references/merged-openrouter-video-input/openrouter-video-input.md` (+ 1 supporting file in that folder).
