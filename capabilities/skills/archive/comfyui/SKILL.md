---
name: comfyui
description: "Generate images, video, and audio with ComfyUI — install, launch, manage nodes/models, run workflows with parameter injection. Uses the official comfy-cli for lifecycle and direct REST/WebSocket API for execution."
version: 5.0.0
author: [kshitijk4poor, alt-glitch]
license: MIT
platforms: [macos, linux, windows]
compatibility: "Requires ComfyUI (local, Comfy Desktop, or Comfy Cloud) and comfy-cli (auto-installed via pipx/uvx by the setup script)."
prerequisites:
  commands: ["python3"]
setup:
  help: "Run scripts/hardware_check.py FIRST to decide local vs Comfy Cloud; then scripts/comfyui_setup.sh auto-installs locally (or use Cloud API key for platform.comfy.org)."
metadata:
  hermes:
    tags:
      - comfyui
      - image-generation
      - stable-diffusion
      - flux
      - sd3
      - wan-video
      - hunyuan-video
      - creative
      - generative-ai
      - video-generation
    related_skills: [stable-diffusion-image-generation, image_gen]
    category: creative
---

# ComfyUI

Generate images, video, audio, and 3D content through ComfyUI using the
official `comfy-cli` for setup/lifecycle and direct REST/WebSocket API
for workflow execution.

## What's in this skill

**Reference docs (`references/`):**

- `official-cli.md` — every `comfy ...` command, with flags
- `rest-api.md` — REST + WebSocket endpoints (local + cloud), payload schemas
- `workflow-format.md` — API-format JSON, common node types, param mapping
- `cloudflare-tunnel-integration.md` — expose ComfyUI via custom domain using Cloudflare Named Tunnels
- `fal-integration.md` — CPU-only setup with Fal.ai custom nodes for GPU offloading
- `custom-node-frontend-loader.md` — expose domain-specific nodes/workflows inside the original ComfyUI UI with `WEB_DIRECTORY`, a frontend loader button, and optional autoload URL

**Scripts (`scripts/`):**

| Script | Purpose |
|--------|---------|
| `_common.py` | Shared HTTP, cloud routing, node catalogs (don't run directly) |
| `hardware_check.py` | Probe GPU/VRAM/disk → recommend local vs Comfy Cloud |
| `comfyui_setup.sh` | Hardware check + comfy-cli + ComfyUI install + launch + verify |
| `extract_schema.py` | Read a workflow → list controllable params + model deps |
| `check_deps.py` | Check workflow against running server → list missing nodes/models |
| `auto_fix_deps.py` | Run check_deps then `comfy node install` / `comfy model download` |
| `run_workflow.py` | Inject params, submit, monitor, download outputs (HTTP or WS) |
| `run_batch.py` | Submit a workflow N times with sweeps, parallel up to your tier |
| `ws_monitor.py` | Real-time WebSocket viewer for executing jobs (live progress) |
| `health_check.py` | Verification checklist runner — comfy-cli + server + models + smoke test |
| `fetch_logs.py` | Pull traceback / status messages for a given prompt_id |
| `fal_sana_executor.py` | Fire-and-forget Fal.ai Sana generation via local ComfyUI API (CPU-only servers) |

**Templates (`templates/`):**

- `fal-sana-workflow.json` — starter API-format workflow using `Sana_fal` node for CPU-only servers with Fal.ai offloading

**Example workflows (`workflows/`):** SD 1.5, SDXL, Flux Dev, SDXL img2img,
SDXL inpaint, ESRGAN upscale, AnimateDiff video, Wan T2V. See
`workflows/README.md`.

## When to Use

- User asks to generate images with Stable Diffusion, SDXL, Flux, SD3, etc.
- User wants to run a specific ComfyUI workflow file
- User wants to chain generative steps (txt2img → upscale → face restore)
- User needs ControlNet, inpainting, img2img, or other advanced pipelines
- User wants to run ComfyUI on a **CPU-only server** and offload generation to **Fal.ai** via custom nodes
- User asks to manage ComfyUI queue, check models, or install custom nodes
- User needs a custom/domain-specific workflow embedded in the **original ComfyUI interface** with custom nodes, a loader button, or an autoload URL
- User wants video/audio/3D generation via AnimateDiff, Hunyuan, Wan, AudioCraft, etc.

## Architecture: Two Layers

```
┌─────────────────────────────────────────────────────┐
│ Layer 1: comfy-cli (official lifecycle tool)        │
│   Setup, server lifecycle, custom nodes, models     │
│   → comfy install / launch / stop / node / model    │
└─────────────────────────┬───────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────┐
│ Layer 2: REST/WebSocket API + skill scripts         │
│   Workflow execution, param injection, monitoring   │
│   POST /api/prompt, GET /api/view, WS /ws           │
│   → run_workflow.py, run_batch.py, ws_monitor.py    │
└─────────────────────────────────────────────────────┘
```

**Why two layers?** The official CLI is excellent for installation and server
management but has minimal workflow execution support. The REST/WS API fills
that gap — the scripts handle param injection, execution monitoring, and
output download that the CLI doesn't do.

## Quick Start

### Detect environment

```bash
# What's available?
command -v comfy >/dev/null 2>&1 && echo "comfy-cli: installed"
curl -s http://127.0.0.1:8188/system_stats 2>/dev/null && echo "server: running"

# Can this machine run ComfyUI locally? (GPU/VRAM/disk check)
python3 scripts/hardware_check.py
```

If nothing is installed, see **Setup & Onboarding** below — but always run the
hardware check first.

### One-line health check

```bash
python3 scripts/health_check.py
# → JSON: comfy_cli on PATH? server reachable? at least one checkpoint? smoke-test passes?
```

## Core Workflow

### Step 1: Get a workflow JSON in API format

Workflows must be in API format (each node has `class_type`). They come from:

- ComfyUI web UI → **Workflow → Export (API)** (newer UI) or
  the legacy "Save (API Format)" button (older UI)
- This skill's `workflows/` directory (ready-to-run examples)
- Community downloads (civitai, Reddit, Discord) — usually editor format,
  must be loaded into ComfyUI then re-exported

Editor format (top-level `nodes` and `links` arrays) is **not directly
executable**. The scripts detect this and tell you to re-export.

### Step 2: See what's controllable

```bash
python3 scripts/extract_schema.py workflow_api.json --summary-only
# → {"parameter_count": 12, "has_negative_prompt": true, "has_seed": true, ...}

python3 scripts/extract_schema.py workflow_api.json
# → full schema with parameters, model deps, embedding refs
```

### Step 3: Run with parameters

```bash
# Local (defaults to http://127.0.0.1:8188)
python3 scripts/run_workflow.py \
  --workflow workflow_api.json \
  --args '{"prompt": "a beautiful sunset over mountains", "seed": -1, "steps": 30}' \
  --output-dir ./outputs

# Cloud (export API key once; uses correct /api routing automatically)
export COMFY_CLOUD_API_KEY="comfyui-..."
python3 scripts/run_workflow.py \
  --workflow workflow_api.json \
  --args '{"prompt": "..."}' \
  --host https://cloud.comfy.org \
  --output-dir ./outputs

# Real-time progress via WebSocket (requires `pip install websocket-client`)
python3 scripts/run_workflow.py \
  --workflow flux_dev.json \
  --args '{"prompt": "..."}' \
  --ws

# img2img / inpaint: pass --input-image to upload + reference automatically
python3 scripts/run_workflow.py \
  --workflow sdxl_img2img.json \
  --input-image image=./photo.png \
  --args '{"prompt": "make it watercolor", "denoise": 0.6}'

# Batch / sweep: 8 random seeds, parallel up to cloud tier limit
python3 scripts/run_batch.py \
  --workflow sdxl.json \
  --args '{"prompt": "abstract"}' \
  --count 8 --randomize-seed --parallel 3 \
  --output-dir ./outputs/batch
```

`-1` for `seed` (or omitting it with `--randomize-seed`) generates a fresh
random seed per run.

### Step 4: Present results

The scripts emit JSON to stdout describing every output file:

```json
{
  "status": "success",
  "prompt_id": "abc-123",
  "outputs": [
    {"file": "./outputs/sdxl_00001_.png", "node_id": "9",
     "type": "image", "filename": "sdxl_00001_.png"}
  ]
}
```

## Decision Tree

| User says | Tool | Command |
|-----------|------|---------|
| **Lifecycle (use comfy-cli)** | | |
| "install ComfyUI" | comfy-cli | `bash scripts/comfyui_setup.sh` |
| "start ComfyUI" | comfy-cli | `comfy launch --background` |
| "stop ComfyUI" | comfy-cli | `comfy stop` |
| "install X node" | comfy-cli | `comfy node install <name>` |
| "download X model" | comfy-cli | `comfy model download --url <url> --relative-path models/checkpoints` |
| "list installed models" | comfy-cli | `comfy model list` |
| "list installed nodes" | comfy-cli | `comfy node show installed` |
| **Execution (use scripts)** | | |
| "is everything ready?" | script | `health_check.py` (optionally with `--workflow X --smoke-test`) |
| "what can I change in this workflow?" | script | `extract_schema.py W.json` |
| "check if W's deps are met" | script | `check_deps.py W.json` |
| "fix missing deps" | script | `auto_fix_deps.py W.json` |
| "generate an image" | script | `run_workflow.py --workflow W --args '{...}'` |
| "use this image" (img2img) | script | `run_workflow.py --input-image image=./x.png ...` |
| "8 variations with random seeds" | script | `run_batch.py --count 8 --randomize-seed ...` |
| "show me live progress" | script | `ws_monitor.py --prompt-id <id>` |
| "fetch the error from job X" | script | `fetch_logs.py <prompt_id>` |
| **Direct REST** | | |
| "what's in the queue?" | REST | `curl http://HOST:8188/queue` (local) or `--host https://cloud.comfy.org` |
| "cancel that" | REST | `curl -X POST http://HOST:8188/interrupt` |
| "generate on CPU via Fal.ai" | REST | Submit `Sana_fal` / `FluxPro_fal` workflow to local ComfyUI; node calls Fal.ai API internally |
| "is Fal.ai connected?" | script | `curl http://HOST:PORT/api/object_info/Sana_fal` or run `fal_sana_workflow.json` smoke test |

## Setup & Onboarding

When a user asks to set up ComfyUI, **the FIRST thing to do is ask whether
they want Comfy Cloud (hosted, zero install, API key) or Local (install
ComfyUI on their machine)**. Don't start running install commands or hardware
checks until they've answered.

**Official docs:** https://docs.comfy.org/installation
**CLI docs:** https://docs.comfy.org/comfy-cli/getting-started
**Cloud docs:** https://docs.comfy.org/get_started/cloud
**Cloud API:** https://docs.comfy.org/development/cloud/overview

### Step 0: Ask Local vs Cloud (ALWAYS FIRST)

Suggested script:

> "Do you want to run ComfyUI locally on your machine, or use Comfy Cloud?
>
> - **Comfy Cloud** — hosted on RTX 6000 Pro GPUs, all common models pre-installed,
>   zero setup. Requires an API key (paid subscription required to actually run
>   workflows; free tier is read-only). Best if you don't have a capable GPU.
> - **Local** — free, but your machine MUST meet the hardware requirements:
>   - NVIDIA GPU with **≥6 GB VRAM** (≥8 GB for SDXL, ≥12 GB for Flux/video), OR
>   - AMD GPU with ROCm support (Linux), OR
>   - Apple Silicon Mac (M1+) with **≥16 GB unified memory** (≥32 GB recommended).
>   - Intel Macs and machines with no GPU will NOT work — use Cloud instead.
>
> Which would you like?"

Routing:

- **Cloud** → skip to **Path A**.
- **Local** → run hardware check first, then pick a path from Paths B–E based on the verdict.
- **Unsure** → run the hardware check and let the verdict decide.

### Step 1: Verify Hardware (ONLY if user chose local)

```bash
python3 scripts/hardware_check.py --json
# Optional: also probe `torch` for actual CUDA/MPS:
python3 scripts/hardware_check.py --json --check-pytorch
```

| Verdict    | Meaning                                                       | Action |
|------------|---------------------------------------------------------------|--------|
| `ok`       | ≥8 GB VRAM (discrete) OR ≥32 GB unified (Apple Silicon)       | Local install — use `comfy_cli_flag` from report |
| `marginal` | SD1.5 works; SDXL tight; Flux/video unlikely                  | Local OK for light workflows, else **Path A (Cloud)** |
| `cloud`    | No usable GPU, <6 GB VRAM, <16 GB Apple unified, Intel Mac, Rosetta Python | **Switch to Cloud** unless user explicitly forces local |

The script also surfaces `wsl: true` (WSL2 with NVIDIA passthrough) and
`rosetta: true` (x86_64 Python on Apple Silicon — must reinstall as ARM64).

If verdict is `cloud` but the user wants local, do not proceed silently.
Show the `notes` array verbatim and ask whether they want to (a) switch to
Cloud or (b) force a local install (will OOM or be unusably slow on modern models).

### Choosing an Installation Path

Use the hardware check first. The table below is the fallback for when the
user has already told you their hardware:

| Situation | Recommended Path |
|-----------|------------------|
| `verdict: cloud` from hardware check | **Path A: Comfy Cloud** |
| No GPU / want to try without commitment | **Path A: Comfy Cloud** |
| Windows + NVIDIA + non-technical | **Path B: ComfyUI Desktop** |
| Windows + NVIDIA + technical | **Path C: Portable** or **Path D: comfy-cli** |
| Linux + any GPU | **Path D: comfy-cli** (easiest) |
| macOS + Apple Silicon | **Path B: Desktop** or **Path D: comfy-cli** |
| Headless / server / CI / agents | **Path D: comfy-cli** |
| CPU-only server + external execution | **Path F: Headless Editor + Cloud Tunnel** |

---

### Path F: Headless Workflow Editor + Cloudflare Tunnel (CPU-Only)

For servers without GPU where the user wants:
1. A local ComfyUI instance to **design and edit workflows** (drag-and-drop node graph)
2. Expose the UI securely via a **custom domain** through Cloudflare
3. Offload actual **generation to external APIs** (Fal.ai, Comfy Cloud, RunPod, Modal)

This is NOT for local generation — CPU-only PyTorch will take 10-30 min per image.

**Steps:**

```bash
# 1. Install ComfyUI with CPU flag
uvx --from comfy-cli comfy --skip-prompt install --cpu

# 2. Launch on 0.0.0.0 so cloudflared can reach it
uvx --from comfy-cli comfy launch --background -- --listen 0.0.0.0 --port 8188 --cpu
# Or via systemd for persistence
```

**Systemd service (CPU-only, headless):**
```ini
# /etc/systemd/system/comfyui.service
[Unit]
Description=ComfyUI Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/comfy/ComfyUI
ExecStart=/root/comfy/ComfyUI/.venv/bin/python main.py --listen 0.0.0.0 --port 8188 --cpu
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

**3. Expose via Cloudflare Named Tunnel**

Create a named tunnel, point a subdomain (e.g. `comfy.example.com`) to `http://localhost:8188`,
run `cloudflared tunnel --config config.yml run`, and persist with systemd.
See `references/cloudflare-tunnel-integration.md` for full copy-paste commands.

**4. Execute workflows externally**

Design workflows in the web UI, export to API format, then run via:
- Fal.ai API (fastest, pay-per-use)
- Comfy Cloud (managed ComfyUI with GPU)
- `run_workflow.py --host https://cloud.comfy.org` (with `COMFY_CLOUD_API_KEY`)

---

### Path F: Headless Workflow Editor + Cloudflare Tunnel (CPU-Only)

For servers without GPU where the user wants:
1. A local ComfyUI instance to **design and edit workflows** (drag-and-drop node graph)
2. Expose the UI securely via a **custom domain** through Cloudflare
3. Offload actual **generation to external APIs** (Fal.ai, Comfy Cloud, RunPod, Modal)

This is NOT for local generation — CPU-only PyTorch will take 10-30 min per image.

**Steps:**

```bash
# 1. Install ComfyUI with CPU flag
uvx --from comfy-cli comfy --skip-prompt install --cpu

# 2. Launch on 0.0.0.0 so cloudflared can reach it
uvx --from comfy-cli comfy launch --background -- --listen 0.0.0.0 --port 8188 --cpu
# Or via systemd for persistence
```

**Systemd service (CPU-only, headless):**
```ini
# /etc/systemd/system/comfyui.service
[Unit]
Description=ComfyUI Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/comfy/ComfyUI
ExecStart=/root/comfy/ComfyUI/.venv/bin/python main.py --listen 0.0.0.0 --port 8188 --cpu
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

**3. Expose via Cloudflare Named Tunnel**

Create a named tunnel, point a subdomain (e.g. `comfy.example.com`) to `http://localhost:8188`,
run `cloudflared tunnel --config config.yml run`, and persist with systemd.
See `references/cloudflare-tunnel-integration.md` for full copy-paste commands.

**4. Execute workflows externally**

Design workflows in the web UI, export to API format, then run via:
- Fal.ai API (fastest, pay-per-use) — install `ComfyUI-fal-API` custom nodes, see `references/fal-integration.md`
- Comfy Cloud (managed ComfyUI with GPU)
- `run_workflow.py --host https://cloud.comfy.org` (with `COMFY_CLOUD_API_KEY`)

---

For the fully automated path (hardware check → install → launch → verify):

```bash
bash scripts/comfyui_setup.sh
# Or with overrides:
bash scripts/comfyui_setup.sh --m-series --port=8190 --workspace=/data/comfy
```

It runs `hardware_check.py` internally, refuses to install locally when the
verdict is `cloud` (unless `--force-cloud-override`), picks the right
`comfy-cli` flag, and prefers `pipx`/`uvx` over global `pip` to avoid polluting
system Python.

---

### Path A: Comfy Cloud (No Local Install)

For users without a capable GPU or who want zero setup. Hosted on RTX 6000 Pro.

**Docs:** https://docs.comfy.org/get_started/cloud

1. Sign up at https://comfy.org/cloud
2. Generate an API key at https://platform.comfy.org/login
3. Set the key:
   ```bash
   export COMFY_CLOUD_API_KEY="comfyui-xxxxxxxxxxxx"
   ```
4. Run workflows:
   ```bash
   python3 scripts/run_workflow.py \
     --workflow workflows/flux_dev_txt2img.json \
     --args '{"prompt": "..."}' \
     --host https://cloud.comfy.org \
     --output-dir ./outputs
   ```

**Pricing:** https://www.comfy.org/cloud/pricing
**Concurrent jobs:** Free/Standard 1, Creator 3, Pro 5. Free tier
**cannot run workflows via API** — only browse models. Paid subscription
required for `/api/prompt`, `/api/upload/*`, `/api/view`, etc.

---

### Path B: ComfyUI Desktop (Windows / macOS)

One-click installer for non-technical users. Currently Beta.

**Docs:** https://docs.comfy.org/installation/desktop
- **Windows (NVIDIA):** https://download.comfy.org/windows/nsis/x64
- **macOS (Apple Silicon):** https://comfy.org

Linux is **not supported** for Desktop — use Path D.

---

### Path C: ComfyUI Portable (Windows Only)

**Docs:** https://docs.comfy.org/installation/comfyui_portable_windows

Download from https://github.com/comfyanonymous/ComfyUI/releases, extract,
run `run_nvidia_gpu.bat`. Update via `update/update_comfyui_stable.bat`.

---

### Path D: comfy-cli (All Platforms — Recommended for Agents)

The official CLI is the best path for headless/automated setups.

**Docs:** https://docs.comfy.org/comfy-cli/getting-started

#### Install comfy-cli

```bash
# Recommended:
pipx install comfy-cli
# Or use uvx without installing:
uvx --from comfy-cli comfy --help
# Or (if pipx/uvx unavailable):
pip install --user comfy-cli
```

Disable analytics non-interactively:
```bash
comfy --skip-prompt tracking disable
```

#### Install ComfyUI

```bash
comfy --skip-prompt install --nvidia              # NVIDIA (CUDA)
comfy --skip-prompt install --amd                 # AMD (ROCm, Linux)
comfy --skip-prompt install --m-series            # Apple Silicon (MPS)
comfy --skip-prompt install --cpu                 # CPU only (slow)
comfy --skip-prompt install --nvidia --fast-deps  # uv-based dep resolution
```

Default location: `~/comfy/ComfyUI` (Linux), `~/Documents/comfy/ComfyUI`
(macOS/Win). Override with `comfy --workspace /custom/path install`.

#### Launch / verify

```bash
comfy launch --background                       # background daemon on :8188
comfy launch -- --listen 0.0.0.0 --port 8190    # LAN-accessible custom port
curl -s http://127.0.0.1:8188/system_stats      # health check
```

---

### Path E: Manual Install (Advanced / Unsupported Hardware)

For Ascend NPU, Cambricon MLU, Intel Arc, or other unsupported hardware.

**Docs:** https://docs.comfy.org/installation/manual_install

```bash
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu130
pip install -r requirements.txt
python main.py
```

---

### Post-Install: Download Models

```bash
# SDXL (general purpose, ~6.5 GB)
comfy model download \
  --url "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors" \
  --relative-path models/checkpoints

# SD 1.5 (lighter, ~4 GB, good for 6 GB cards)
comfy model download \
  --url "https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors" \
  --relative-path models/checkpoints

# Flux Dev fp8 (smaller variant, ~12 GB)
comfy model download \
  --url "https://huggingface.co/Comfy-Org/flux1-dev/resolve/main/flux1-dev-fp8.safetensors" \
  --relative-path models/checkpoints

# CivitAI (set token first):
comfy model download \
  --url "https://civitai.com/api/download/models/128713" \
  --relative-path models/checkpoints \
  --set-civitai-api-token "YOUR_TOKEN"
```

List installed: `comfy model list`.

### Post-Install: Install Custom Nodes

```bash
comfy node install comfyui-impact-pack             # popular utility pack
comfy node install comfyui-animatediff-evolved     # video generation
comfy node install comfyui-controlnet-aux          # ControlNet preprocessors
comfy node install comfyui-essentials              # common helpers
comfy node update all
comfy node install-deps --workflow=workflow.json   # install everything a workflow needs
```

### Post-Install: Verify

```bash
python3 scripts/health_check.py
# → comfy_cli on PATH? server reachable? checkpoints? smoke test?

python3 scripts/check_deps.py my_workflow.json
# → are this workflow's nodes/models/embeddings installed?

python3 scripts/run_workflow.py \
  --workflow workflows/sd15_txt2img.json \
  --args '{"prompt": "test", "steps": 4}' \
  --output-dir ./test-outputs
```

## Image Upload (img2img / Inpainting)

The simplest way is to use `--input-image` with `run_workflow.py`:

```bash
python3 scripts/run_workflow.py \
  --workflow workflows/sdxl_img2img.json \
  --input-image image=./photo.png \
  --args '{"prompt": "make it cyberpunk", "denoise": 0.6}'
```

The flag uploads `photo.png`, then injects its server-side filename into
whatever schema parameter is named `image`. For inpainting, pass both:

```bash
python3 scripts/run_workflow.py \
  --workflow workflows/sdxl_inpaint.json \
  --input-image image=./photo.png \
  --input-image mask_image=./mask.png \
  --args '{"prompt": "fill with flowers"}'
```

Manual upload via REST:
```bash
curl -X POST "http://127.0.0.1:8188/upload/image" \
  -F "image=@photo.png" -F "type=input" -F "overwrite=true"
# Returns: {"name": "photo.png", "subfolder": "", "type": "input"}

# Cloud equivalent:
curl -X POST "https://cloud.comfy.org/api/upload/image" \
  -H "X-API-Key: $COMFY_CLOUD_API_KEY" \
  -F "image=@photo.png" -F "type=input" -F "overwrite=true"
```

## Cloud Specifics

- **Base URL:** `https://cloud.comfy.org`
- **Auth:** `X-API-Key` header (or `?token=KEY` for WebSocket)
- **API key:** set `$COMFY_CLOUD_API_KEY` once and the scripts pick it up automatically
- **Output download:** `/api/view` returns a 302 to a signed URL; the scripts
  follow it and strip `X-API-Key` before fetching from the storage backend
  (don't leak the API key to S3/CloudFront).
- **Endpoint differences from local ComfyUI:**
  - `/api/object_info`, `/api/queue`, `/api/userdata` — **403 on free tier**;
    paid only.
  - `/history` is renamed to `/history_v2` on cloud (the scripts route
    automatically).
  - `/models/<folder>` is renamed to `/experiment/models/<folder>` on cloud
    (the scripts route automatically).
  - `clientId` in WebSocket is currently ignored — all connections for a
    user receive the same broadcast. Filter by `prompt_id` client-side.
  - `subfolder` is accepted on uploads but ignored — cloud has a flat namespace.
- **Concurrent jobs:** Free/Standard: 1, Creator: 3, Pro: 5. Extras queue
  automatically. Use `run_batch.py --parallel N` to saturate your tier.

## Queue & System Management

```bash
# Local
curl -s http://127.0.0.1:8188/queue | python3 -m json.tool
curl -X POST http://127.0.0.1:8188/queue -d '{"clear": true}'    # cancel pending
curl -X POST http://127.0.0.1:8188/interrupt                      # cancel running
curl -X POST http://127.0.0.1:8188/free \
  -H "Content-Type: application/json" \
  -d '{"unload_models": true, "free_memory": true}'

# Cloud — same paths under /api/, plus:
python3 scripts/fetch_logs.py --tail-queue --host https://cloud.comfy.org
```

## DynamicCombo Nodes (ComfyUI Native API Nodes)

Some nodes bundled with ComfyUI — like `HappyHorseTextToVideoApi` — are **NOT**
Fal.ai nodes. They are native ComfyUI "API nodes" that call ComfyOrg's own
hosted endpoints. These require `auth_token_comfy_org` and will fail with:

```
Unauthorized: Please login first to use this node.
```

### Input format for DynamicCombo nodes

DynamicCombo nodes expose nested inputs based on the selected model. In API
format, use **dot-notation** prefixed with the combo key:

```json
{
  "1": {
    "class_type": "HappyHorseTextToVideoApi",
    "inputs": {
      "model": "happyhorse-1.0-t2v",
      "model.prompt": "a waterfall",
      "model.resolution": "720P",
      "model.ratio": "16:9",
      "model.duration": 5,
      "seed": 42,
      "watermark": false
    }
  }
}
```

Submitting flat keys (`"prompt": "..."`) will trigger:

```json
{
  "type": "required_input_missing",
  "details": "prompt",
  "extra_info": {"input_name": "model.prompt"}
}
```

**Rule:** If `class_type` does NOT end in `_fal`, it is likely a native
ComfyUI node with different auth and input requirements.

## Output Type Mismatch: STRING vs IMAGE/VIDEO

Fal.ai nodes (`Kling_fal`, `SeedanceTextToVideo_fal`) return `STRING` (a URL),
not `IMAGE` or `VIDEO` tensors. This means you **cannot** wire them directly
to `SaveImage` or `SaveVideo`. Solutions:

### Option A: Custom SaveString node

Create `custom_nodes/save_string_node/__init__.py`:

```python
import os

class SaveString:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"forceInput": True}),
                "filename": ("STRING", {"default": "output.txt"}),
            }
        }
    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "save"
    CATEGORY = "utils"

    def save(self, text, filename):
        path = os.path.join("/root/comfy/ComfyUI/output", filename)
        with open(path, "w") as f:
            f.write(str(text))
        return ()

NODE_CLASS_MAPPINGS = {"SaveString": SaveString}
NODE_DISPLAY_NAME_MAPPINGS = {"SaveString": "Save String"}
```

Then wire:
```json
{
  "1": {"class_type": "Kling_fal", "inputs": {...}},
  "2": {
    "class_type": "SaveString",
    "inputs": {
      "text": ["1", 0],
      "filename": "kling_url.txt"
    }
  }
}
```

After execution, read `/root/comfy/ComfyUI/output/kling_url.txt` for the URL.

### Option B: Direct curl download

After polling `/api/history/<prompt_id>` and confirming `execution_success`,
read the URL from node output and download with `curl -o output.mp4 <url>`.

## Pitfalls

1. **API format required** — every script and the `/api/prompt` endpoint expect
   API-format workflow JSON. The scripts detect editor format (top-level
   `nodes` and `links` arrays) and tell you to re-export via
   "Workflow → Export (API)" (newer UI) or "Save (API Format)" (older UI).

1a. **DynamicCombo nodes need nested input format** — Nodes like `HappyHorseTextToVideoApi`
   use `DynamicCombo` inputs where the actual params are nested under the combo key.
   In API format, use dot-notation: `model.prompt`, `model.resolution`, `model.ratio`,
   `model.duration` — NOT flat `prompt`, `resolution`, etc. Example:
   ```json
   "inputs": {
     "model": "happyhorse-1.0-t2v",
     "model.prompt": "a waterfall",
     "model.resolution": "720P",
     "model.ratio": "16:9",
     "model.duration": 5,
     "seed": 42,
     "watermark": false
   }
   ```
   Submitting flat keys will trigger `required_input_missing` errors for
   `model.prompt`, `model.resolution`, etc.

1b. **ComfyOrg nodes ≠ Fal.ai nodes** — `HappyHorseTextToVideoApi` is a **native
   ComfyUI node** (lives in `comfy_api_nodes/nodes_wan.py`), NOT a Fal.ai node.
   It requires ComfyOrg login (`auth_token_comfy_org`) and returns `VIDEO` type.
   True Fal.ai nodes (`Sana_fal`, `Kling_fal`, `SeedanceTextToVideo_fal`) live in
   `custom_nodes/ComfyUI-fal-API/` and call Fal.ai's API internally. Do not
   confuse the two — they have different auth, different outputs, and different
   input schemas.

2. **Server must be running** — all execution requires a live server.
   `comfy launch --background` starts one. Verify with
   `curl http://127.0.0.1:8188/system_stats`.

3. **Model names are exact** — case-sensitive, includes file extension.
   `check_deps.py` does fuzzy matching (with/without extension and folder
   prefix), but the workflow itself must use the canonical name. Use
   `comfy model list` to discover what's installed.

4. **Missing custom nodes** — "class_type not found" means a required node
   isn't installed. `check_deps.py` reports which package to install;
   `auto_fix_deps.py` runs the install for you.

5. **Working directory** — `comfy-cli` auto-detects the ComfyUI workspace.
   If commands fail with "no workspace found", use
   `comfy --workspace /path/to/ComfyUI <command>` or
   `comfy set-default /path/to/ComfyUI`.

6. **Cloud free-tier API limits** — `/api/prompt`, `/api/view`, `/api/upload/*`,
   `/api/object_info` all return 403 on free accounts. `health_check.py` and
   `check_deps.py` handle this gracefully and surface a clear message.

7. **Timeout for video/audio workflows** — auto-detected when an output node
   is `VHS_VideoCombine`, `SaveVideo`, etc.; the default jumps from 300 s to
   900 s. Override explicitly with `--timeout 1800`.

8. **Path traversal in output filenames** — server-supplied filenames are
   passed through `safe_path_join` to refuse anything escaping `--output-dir`.
   Keep this protection on — workflows with custom save nodes can produce
   arbitrary paths.

9. **Workflow JSON is arbitrary code** — custom nodes run Python, so
   submitting an unknown workflow has the same trust profile as `eval`.
   Inspect workflows from untrusted sources before running.

10. **Auto-randomized seed** — pass `seed: -1` in `--args` (or use
    `--randomize-seed` and omit the seed) to get a fresh seed per run.
    The actual seed is logged to stderr.

11. **`tracking` prompt** — first run of `comfy` may prompt for analytics.
    Use `comfy --skip-prompt tracking disable` to skip non-interactively.
    `comfyui_setup.sh` does this for you.
12. **CPU-only is for editing only** — Installing with `--cpu` on a headless
    server is useful for workflow design and API-format export, but actual
    image/video generation will be excruciatingly slow (10-30 min/image).
    Always pair CPU installs with external execution (Fal.ai, Comfy Cloud,
    RunPod). Never let the user expect usable local generation without GPU.

12a. **Fal.ai nodes output STRING URLs, not tensors** — Nodes like `Kling_fal`
    and `SeedanceTextToVideo_fal` return `STRING` (a download URL), not `IMAGE`
    or `VIDEO`. You cannot wire them directly to `SaveImage` or `SaveVideo`.
    Either:
    - Create a custom `SaveString` node (see `scripts/save_string_node.py`) to
      write the URL to a text file, then download separately.
    - Use the URL directly with `curl -o output.mp4 <url>`.
    - Chain to `LoadImageFromURL_fal` if the node pack supports it.

12b. **`comfy` CLI may not be on PATH** — When installing via `uvx`, the
    `comfy` binary lives in a temp cache and may vanish. For installing
    custom nodes, fall back to `git clone` into `custom_nodes/` directly:
    ```bash
    cd ComfyUI/custom_nodes && git clone https://github.com/OWNER/REPO.git
    source ../.venv/bin/activate && pip install -r REPO/requirements.txt
    ```

12c. **Video generation timeout** — Fal.ai video jobs (Kling, Seedance) take
    5-8 min. The default `run_workflow.py` timeout (300s) is insufficient.
    Use `--timeout 600` or poll history manually with longer intervals.

13. **Web UI starts empty** — The ComfyUI canvas does NOT auto-load any workflow.
    Workflows saved to `user/default/workflows/` appear in the Load menu but
    must be clicked manually. There is no "default startup workflow" file.
    To make a workflow open automatically inside the original UI, add a custom
    node frontend extension with `WEB_DIRECTORY = "./web"`, serve editor-format
    JSON from `/extensions/<package>/<workflow>.json`, and call `app.loadGraphData()`
    from a loader button or query-param autoload. See `references/custom-node-frontend-loader.md`.
14. **API format vs Editor format are different** — The REST `/api/prompt`
    endpoint requires API format (`class_type` keys). The web UI's Save/Load
    uses Editor format (`nodes`/`links` arrays). To run a workflow from the
    editor in the API, you must re-export it via "Workflow → Export (API)".
    Conversely, editor-format files cannot be submitted to `/api/prompt`.
15. **`comfy` CLI may not be on PATH** — When installing via `uvx`, the
    `comfy` binary lives in a temp cache and may vanish. For installing
    custom nodes, fall back to `git clone` into `custom_nodes/` directly:
    ```bash
    cd ComfyUI/custom_nodes && git clone https://github.com/OWNER/REPO.git
    source ../.venv/bin/activate && pip install -r REPO/requirements.txt
    ```
14. **API format vs Editor format are different** — The REST `/api/prompt`
    endpoint requires API format (`class_type` keys). The web UI's Save/Load
    uses Editor format (`nodes`/`links` arrays). To run a workflow from the
    editor in the API, you must re-export it via "Workflow → Export (API)".
    Conversely, editor-format files cannot be submitted to `/api/prompt`.
15. **`comfy` CLI may not be on PATH** — When installing via `uvx`, the
    `comfy` binary lives in a temp cache and may vanish. For installing
    custom nodes, fall back to `git clone` into `custom_nodes/` directly:
    ```bash
    cd ComfyUI/custom_nodes && git clone https://github.com/OWNER/REPO.git
    source ../.venv/bin/activate && pip install -r REPO/requirements.txt
    ```

## Verification Checklist

Use `python3 scripts/health_check.py` to run the whole list at once. Manual:

- [ ] `hardware_check.py` verdict is `ok` OR the user explicitly chose Comfy Cloud
- [ ] `comfy --version` works (or `uvx --from comfy-cli comfy --help`)
- [ ] `curl http://HOST:PORT/system_stats` returns JSON
- [ ] `comfy model list` shows at least one checkpoint (local) OR
      `/api/experiment/models/checkpoints` returns models (cloud)
- [ ] Workflow JSON is in API format
- [ ] `check_deps.py` reports `is_ready: true` (or only `node_check_skipped`
      on cloud free tier)
- [ ] Test run with a small workflow completes; outputs land in `--output-dir`
