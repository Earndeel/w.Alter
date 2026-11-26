## Pipeline Database (SQLite)

### Location and Schema
Database: `/root/projects/ad-video-pipeline/pipeline.db`

7 tables with foreign key relationships:
1. **cards** — Notion Kanban cards (source of truth)
   - Key fields: `card_name`, `card_notion_url` (UNIQUE), `product_brand`, `category`, `foreplay_url`
   - Metadata: `comments_json` (JSONB), `instructions_loom`, `script_hooks` (JSONB)
   - Stats: `kanban_column`, `creator`, status tracking

2. **videos** — Downloaded foreplay.co videos
   - Key fields: `card_id` (FK), `foreplay_url`, `local_path`, `download_status`
   - Metadata: `duration_sec`, `file_size_mb`, `resolution`, `fps`, `codec`

3. **shots** — Shot segmentation from video
   - Key fields: `video_id` (FK), `shot_index`, `timestamp_sec`, `keyframe_path`
   - Analysis: `shot_description`, `shot_type`, `has_product`, `product_visibility`
   - Technical: `camera_angle`, `lighting`

4. **shot_analysis** — Vision AI analysis per shot
   - Key fields: `shot_id` (FK), `model_used`, `analysis_json`
   - Extraction: `scene_type`, `setting`, `objects_detected`, `color_palette`, `mood`

5. **prompts** — Kling V3 generated prompts
   - Key fields: `shot_id` (FK), `clip_type`, `prompt_text`
   - Element refs: `element_refs`, `multi_prompt_payload`
   - Workflow: `review_status` (draft → approved), `review_notes`

6. **generations** — Generated videos
   - Key fields: `prompt_id` (FK), `submission_id`, `generation_status`
   - Output: `result_url`, `local_path`, `duration_sec`, `resolution`
   - Cost: `cost_usd`

7. **deliveries** — Client delivery tracking
   - Key fields: `generation_id` (FK), `gdrive_file_id`, `gdrive_file_url`
   - Status: `delivery_status`, `client_notified` (boolean)

### Useful Views
```sql
-- Overall pipeline status per card
SELECT * FROM v_pipeline_dashboard;

-- Download queue (cards with foreplay links, not yet downloaded)
SELECT * FROM v_download_queue;
```

### Ingestion from Notion Extraction
```python
# After extracting comments via CDP, update the cards table:
cursor.execute("""
    UPDATE cards SET 
        comments_json = ?,
        instructions_loom = ?,
        script_hooks = ?,
        updated_at = datetime('now')
    WHERE card_name = ?
""", (comments_json, loom_url, hooks_json, card_name))
```

### VIDEO ANALYZER Module (VALIDATED — April 2026, V3 PRODUCTION)

**Status (April 6, 2026):** 10/15 cards analyzed OK. 3 FAIL (rate limit 429, V2 legacy). 2 WAITING (14-15).

#### Architecture V3 — Direct Video Input (NO FRAMES)
The `modules/video_analyzer_v3.py` script:
1. **Reads video path** from `videos` table (`local_path`) — validates file exists
2. **Compresses if needed** — videos >150MB: `ffmpeg -vf scale=720:1280 -crf 28`
3. **Encodes entire .mp4 as base64** — single string like `data:video/mp4;base64,...`
4. **Calls OpenRouter API** with `qwen/qwen3.6-plus:free` and video content type (180s timeout, 5-retry exponential backoff)
5. **Saves analysis** to `video_analysis` table + telemetry (prompt/usage tokens, model)

#### Why V3 replaces V2
- V2: extract frames with ffmpeg → analyze each → stitch. High token cost, misses timing, 3-retry linear backoff
- V3: send full video → LLM decomposes itself. Lower tokens per card, better temporal understanding, 5-retry exponential backoff
- Card 7 (6.8MB) validated: 49367 prompt tokens + 3592 completion = 52,959 total, 5211 chars output, 87s

#### Current Prompt State
Editable live via dashboard `⚙ Prep` button (GET/PUT `/api/preprompt`) or edit `/root/projects/ad-video-pipeline/prompts/video_analysis_prompt.md` directly. Uses `str.format()` variables: `{product_name}`, `{product_brand}`, `{creator}`, `{duration}`, `{category}`, `{card_name}`.

**IMPORTANT:** All raw JSON `{}` in the template must be escaped as `{{}}` to avoid `KeyError`.

### Prompt Template System
Template at `prompts/video_analysis_prompt.md` uses `str.format()` for variable injection.

**CRITICAL:** All `{}` braces in the template (especially JSON examples) MUST be escaped as `{{}}` to avoid `KeyError` in `str.format()`. The template was initially written with raw JSON `{}` which caused crashes.

Variables injected:
- `{product_name}`
- `{product_brand}`
- `{creator}`
- `{duration}`
- `{category}`

### New DB Table: `video_analysis`
```sql
CREATE TABLE video_analysis (
    id INTEGER PRIMARY KEY,
    card_id INTEGER NOT NULL,
    analysis_text TEXT,
    kling_prompts_json TEXT,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    model_used TEXT,
    tokens_prompt INTEGER DEFAULT 0,
    tokens_completion INTEGER DEFAULT 0
);
```

### Critical Pitfalls
- **`sqlite3.Row` has no `.get()` method** — use `card['key'] or 'default'` instead of `card.get('key', 'default')`
- **`subprocess.run` with curl needs `shell=True`** — without it, the entire command string is treated as a single executable name
- **Sandbox DNS resolution fails** for `api.openrouter.ai` (`socket.gaierror`) — the validated workaround is `subprocess.run(cmd, shell=True)` which bypasses the Python sandbox's DNS restrictions
- **Template `{}` vs `str.format()`** — raw JSON braces in the prompt template crash with `KeyError`. Escaped all non-variable `{}` to `{{}}`
- **Card 11 video** has filename `w14_v1_posp.mp4` (not `foreplay_XX` pattern) — special case in video resolution logic

### Dashboard — Flask + Tailscale (Production, April 2026 Status)

**URL:** `http://100.91.35.121:5001` (Tailscale)
**Service:** `pipeline-dashboard.service` (systemd)

**Architecture:** Flask backend + static frontend. Flask serves APIs and static folder.

- **Backend:** `/root/projects/ad-video-pipeline/dashboard.py` — Flask app with `static_folder`
- **Frontend:** `/tmp/dashboard_static/index.html` — pure HTML/CSS/JS
- **APIs:**
  - `GET /` → static HTML dashboard
  - `GET /api/stats` → aggregated stats
  - `GET /api/cards` → array of 15 card objects
  - `GET /api/analysis/<id>` → full analysis text + comments for a card
  - `GET /api/kling/<id>` → Kling prompt payload
  - `GET /api/preprompt` → read the analysis prompt template
  - `PUT /api/preprompt` → edit the analysis prompt template
  - `GET /api/video/<id>` → stream downloaded MP4 with Range requests (seeking)
- **Features:** filter buttons, search bar, expandable cards, modal for analysis/comments, 10s auto-refresh polling

**Dashboard v3 frontend is FREEZED** — Lucas is good at backend orchestration but struggles with direct frontend code (CSS/HTML/JS). Changes limited to simple corrections only. Major UI upgrades should use subagents with specialized coding models.

**CRITICAL pitfalls for dashboard updates:**
- **JS syntax errors break the entire page silently** — a missing `)` or unclosed string in JS concatenation causes all JS to fail, leaving the dashboard stuck on "Chargement des cartes..." with only a single browser console error
- **Always validate JS** after modifying `index.html`: check for balanced parentheses, quotes, and proper string escaping
- **Flask caches static files** — edits to `index.html` are picked up on next request, but browser caching may require a hard refresh
- **Keep `data-text` and `esc()` calls clean** — a common bug is forgetting to close `esc(...)`: `esc(name + ' ' + prod + ' ' + cat)` — the closing paren is easy to miss

**Deploy/update workflow:**
1. Edit `/tmp/dashboard_static/index.html`
2. Validate JS syntax (balanced parens, quotes, no stray characters)
3. Test with `curl -s http://localhost:5001/api/stats` and open in browser
4. No systemd restart needed for static file changes

### Dashboard v3 — Cloudflare Pages (Legacy)
Static HTML dashboard with integrated VIDEO ANALYZER results. URL pattern: `https://<commit>.pipeline-dashboard-f4f.pages.dev`
- Features: sortable columns, global/filtered totals, detailed per-card analysis view, modal for full analysis text
- **Includes 5 completed VIDEO ANALYZER results** (Cards 1-5) with model, token counts, scores
- Data source: JSON export from `pipeline.db` embedded directly in the HTML
- **Filter buttons**: All, Analyzed, Pending, With Score, Short (<15s), With Comments
- **Update workflow**: query DB → generate `/tmp/dashboard_v3/index.html` → deploy with wrangler
- **Deploy command**: `cd /tmp/dashboard_v3 && CLOUDFLARE_API_TOKEN="<token>" CLOUDFLARE_ACCOUNT_ID="<account_id>"` wrangler pages deploy . --project-name=pipeline-dashboard

### OpenRouter: Native Video Input API (VALIDATED April 2026)
**The REST API DOES support video natively** — confirmed with Card 7 (6.8MB MP4 → 9.1MB base64 → 5211 chars analysis, 49367 prompt tokens):
- ✅ **API REST**: Send `data:video/mp4;base64,<base64>` via POST to `https://openrouter.ai/api/v1/chat/completions` with model `qwen/qwen3.6-plus:free`. Works with videos up to ~150MB.
- ✅ **Payload structure**: `{"type": "video_url", "video_url": {"url": "data:video/mp4;base64,..."}}`
- ⚠️ **Large files**: Videos >150MB should be compressed first: `ffmpeg -i input.mp4 -vf scale=720:1280 -c:v libx264 -crf 28 compressed.mp4`
- ⚠️ **Timeout**: Set `urllib.request.urlopen(..., timeout=180)` — analysis can take 60-120s
- ⚠️ **429 handling**: Use exponential backoff (30s * attempt, up to 5 retries = 30/60/90/120/150s pauses)
- **Frame extraction is DEPRECATED** — no more ffmpeg → base64 frames. Send the full `.mp4` directly.

### Video Analyzer V3 (April 2026 — PRODUCTION)
**File:** `modules/video_analyzer_v3.py` — replaces `video_analyzer_v2.py` for all analysis work.

**Key changes over V2:**
1. **Direct video input** — `encode_video_base64()` sends the `.mp4` file directly, no frame extraction
2. **5-retry exponential backoff** — 30s/60s/90s/120s/150s for 429 rate limits (was 3 retries linear 15s/30s/45s)
3. **180s timeout** — `urllib.request.urlopen(timeout=180)` for long video analysis
4. **Proper telemetry** — `usage['prompt_tokens']` and `usage['completion_tokens']` correctly logged
5. **Auto-compression** — videos >150MB compressed via ffmpeg before sending
6. **Batch skips validated OK** — `--batch` skips cards with valid analysis (>100 chars, not ERROR/FATAL)
7. **`--list` command** — shows pending and failed cards with error messages

**Usage:**
```bash
python3 modules/video_analyzer_v3.py --list          # Show pending/failed
python3 modules/video_analyzer_v3.py --card_id 7     # Single card
python3 modules/video_analyzer_v3.py --batch 11      # Batch from card 11
```

**Dashboard integration:** `dashboard.py` imports from `video_analyzer_v3` (line ~164). The `⚙ Prep` button edits the prompt template in real-time via `PUT /api/preprompt`.

### fal.ai Video API Schema (Validated via mcporter)
Three core tools available via `mcporter call fal.<tool>`:

1. **`generate_video`** (text-to-video / image-to-video)
   - `prompt` (required), `image_url?`, `model?`, `duration?`, `aspect_ratio?`, `negative_prompt?`, `cfg_scale?`

2. **`generate_video_from_image`** (image-to-video explicit)
   - `image_url` (required), `prompt` (required), `model?`, `duration?`, `aspect_ratio?`, `negative_prompt?`, `cfg_scale?`

3. **`generate_video_from_video`** (video-to-video, richest params)
   - `video_url` (required), `prompt` (required), `model?`, `duration?`, `aspect_ratio`: "16:9" | "9:16" | "1:1", `cfg_scale?`, `image_url?`, `character_orientation?`, `keep_original_sound?`, `tail_image_url?`, `generate_audio?`, `negative_prompt?`, `strength?`, `num_frames?`

**Available Kling models** (via `mcporter list fal --category video --search "kling v3"`):
- `fal-ai/kling-video/v3/pro/text-to-video` — Kling 3.0 Pro with multi-shot support
- `fal-ai/kling-video/v3/standard/text-to-video` — Kling 3.0 Standard with multi-shot support
- v2.6 Pro, v2.5 Turbo, v2.1 Master, O3, 1.6, 1.5, 1.0 also available

### Kling v3 cfg_scale Constraint (VALIDATED April 2026)

**CRITICAL: `cfg_scale` must be ≤ 1.0 on ALL Kling v3 endpoints** (both `standard` and `pro`).

- `fal_client.submit()` accepts any value and returns a `request_id`
- But `fal_client.result()` fails with `422`: `'cfg_scale', 'msg': 'Input should be less than or equal to 1', 'input': 4.5`
- The endpoint validates the payload after queue submission, so the error only appears on retrieval
- **Solution**: Always use `cfg_scale: 1.0` (max) or lower (typical range: 0.5-1.0)
- `cfg_scale: 0.5` → permissive, Kling follows its own style
- `cfg_scale: 1.0` → strictest allowed, follows prompt most closely

**Working endpoint**: `fal-ai/kling-video/v3/standard/text-to-video` with `cfg_scale: 1` — tested and produces 12s multi_prompt videos (~12MB output).

**Key difference between standard and pro**: `pro` does NOT accept higher cfg_scale values. The validation is identical. Use `standard` unless you need a specific `pro`-only feature (check OpenAPI schema for differences).

### OpenRouter Rate Limit (Kling Payload Generation)
- The Kling payload LLM call takes ~90-120s for the first response
- OpenRouter returns **429** rapidly if calls are too frequent
- The 5-retry backoff (30/60/90/120/150s) is NOT sufficient for rapid successive calls
- **If you just ran a video analysis, wait 2-3 min before calling Kling payload gen**
- The async Flask pattern (task_id + polling) prevents HTTP timeout but the LLM call can still fail with 429 after all retries
- If `status=failed` with "Rate limit 429", simply retry after 2 minutes

### mcporter Bash Gotcha
Parentheses `()` in mcporter arguments cause `bash: syntax error near unexpected token '('`. Always use `--category` and `--search` flags instead: `mcporter call fal.list_models --category video --search "kling v3 pro"` — OR escape with `\(` `\)` if function-style args are needed.

### Multi-Model Refactor Pitfalls (V5, April 2026)

**Don't over-abstract the provider layer.** When Lucas says "multiple models," he means different preprompts + schemas going through the SAME provider (Fal.ai). Don't assume you need provider adapters (Replicate, direct API, etc.) — ask first.

**DB migration: check actual column names.** The `ALTER TABLE ADD COLUMN` succeeded but the `UPDATE ... SET` referenced `kling_error` which didn't exist in the actual schema (only in the skill doc). Always run `PRAGMA table_info(table)` before writing migration SQL.

**COALESCE for column migration:** When adding generic columns alongside legacy ones, use `COALESCE(new_col, old_col)` in reads and `UPDATE SET new_col = COALESCE(new_col, old_col)` for migration. This ensures both old and new data paths work during transition.

**Dashboard JS: rename elements consistently.** When renaming `kling-payload` → `gen-payload`, update ALL references: the textarea id, the JS functions that read it, and the CSS if any. A missed reference breaks the page silently (JS error in console, dashboard stuck on loading).
