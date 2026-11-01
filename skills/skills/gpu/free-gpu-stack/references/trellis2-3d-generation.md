# TRELLIS.2 — Microsoft 3D Generation Model

## Overview
- **Repo**: `microsoft/TRELLIS.2` (GitHub, 7.3k stars)
- **Params**: 4B (single model: TRELLIS.2-4B)
- **Resolution**: 512³ to 1536³
- **Input**: Image → 3D (PBR materials: base color, roughness, metallic, opacity)
- **Output**: GLB textured mesh with PBR
- **License**: MIT
- **Representation**: O-Voxel (field-free sparse voxel structure)

## Official Benchmarks (H100 GPU)

| Resolution | Total Time | Shape + Texture |
|---|---|---|
| 512³ | ~3s | 2s + 1s |
| 1024³ | ~17s | 10s + 7s |
| 1536³ | ~60s | 35s + 25s |

## RTX 4090 — Actual Benchmarks (tested May 2026)

**Verified on Vast.ai**: RTX 4090, CUDA 13.2, PyTorch 2.6.0+cu124

| Resolution | H100 (official) | RTX 4090 (measured) | Ratio |
|---|---|---|---|
| 512³ | ~3s | ~15s (estimated) | ~5x |
| 1024³ (cascade) | ~17s | **52.8s** ✅ | ~3x |
| 1536³ | ~60s | ~3min (estimated) | ~3x |

- **Peak VRAM**: 8.6 GB (well within 24GB limit)
- **Output**: 47 MB GLB with PBR textures
- **Pipeline load time**: ~120s first run; ~20s cached
- **Cost per asset at 1024**: $0.67/hr × 52.8s = ~$0.01

## Install on Vast.ai

```bash
git clone -b main https://github.com/microsoft/TRELLIS.2.git --recursive
cd TRELLIS.2
. ./setup.sh --basic --flash-attn --nvdiffrast --nvdiffrec --cumesh --o-voxel --flexgemm
```

**PyTorch image**: Use `pytorch/pytorch:2.6.0-cuda12.4-cudnn9-devel` for CUDA 12.4 natif.

## Gated Models — Full Workflow

TRELLIS.2 loads TWO gated HuggingFace models:

1. **DINOv3** (facebook/dinov3-vitl16-pretrain-lvd1689m) — vision feature extractor
2. **RMBG-2.0** (briaai/RMBG-2.0) — background removal

### Getting access

1. Accept license on each HF model page ("Agree and access repository")
2. Set `HF_TOKEN` on the instance: `export HF_TOKEN="hf_..."`
3. DINOv3 may require manual review by Meta (wait ~1 day)

### Bypassing RMBG-2.0 (3 patches required)

If RMBG-2.0 access is denied, apply ALL THREE patches:

**Patch 1 — Config** (`pipeline.json`):
```python
import json
with open('pipeline.json') as f:
    cfg = json.load(f)
cfg['args']['rembg_model'] = None
with open('pipeline.json', 'w') as f:
    json.dump(cfg, f, indent=4)
```

**Patch 2 — Loading code** (`trellis2/pipelines/trellis2_image_to_3d.py`, ~line 105):
```python
# Change:
pipeline.rembg_model = getattr(rembg, args['rembg_model']['name'])(**args['rembg_model']['args'])
# To:
if args.get('rembg_model') is not None:
    pipeline.rembg_model = getattr(rembg, args['rembg_model']['name'])(**args['rembg_model']['args'])
else:
    pipeline.rembg_model = None
```

**Patch 3 — Preprocessing** (same file, `preprocess_image` method):
```python
# Change:
        if has_alpha:
            output = input
        else:
            input = input.convert('RGB')
            if self.low_vram:
                self.rembg_model.to(self.device)
            output = self.rembg_model(input)
            if self.low_vram:
                self.rembg_model.cpu()
# To:
        if has_alpha:
            output = input
        elif self.rembg_model is not None:
            input = input.convert('RGB')
            if self.low_vram:
                self.rembg_model.to(self.device)
            output = self.rembg_model(input)
            if self.low_vram:
                self.rembg_model.cpu()
        else:
            output = input.convert('RGBA')
```

**Why 3 patches**: Missing Patch 3 → `AttributeError: 'NoneType' object has no attribute 'to'` at runtime in `preprocess_image`.

### DINOv3 architecture fix

`DinoV3FeatureExtractor` accesses layers as `self.model.layer` but DINOv3 wraps them in `self.model.model.layer`. Fix in `trellis2/modules/image_feature_extractor.py`:
```python
# Change:
for i, layer_module in enumerate(self.model.layer):
# To:
for i, layer_module in enumerate(self.model.model.layer):
```

## `from_pretrained` Hub Pitfall

`from_pretrained("microsoft/TRELLIS.2-4B")` always downloads `pipeline.json` from HF hub, ignoring local patches. To use patched config:

```python
# Option A: Download full repo locally
from huggingface_hub import snapshot_download
path = snapshot_download("microsoft/TRELLIS.2-4B", local_dir="/root/TRELLIS.2-4B")
# Patch /root/TRELLIS.2-4B/pipeline.json, then:
pipeline = Trellis2ImageTo3DPipeline.from_pretrained("/root/TRELLIS.2-4B")

# Option B: Download just pipeline.json, patch, symlink model dirs
from huggingface_hub import hf_hub_download
config_path = hf_hub_download("microsoft/TRELLIS.2-4B", "pipeline.json")
# ... patch config, create local dir with symlinks ...
```

## WebP Export Pitfall

`glb.export(out, extension_webp=True)` fails with `AttributeError: module 'PIL._webp' has no attribute 'HAVE_WEBPANIM'`. Fix: `glb.export(out)` without `extension_webp=True`.

## Sending Large GLB to Telegram

GLB files >50MB may fail via `send_message`. Use Telegram Bot API directly:
```bash
curl -s -X POST "https://api.telegram.org/bot<TOKEN>/sendDocument" \
  -F chat_id="<CHAT_ID>" \
  -F document=@"/path/to/file.glb" \
  -F caption="🎮 Asset name | TRELLIS.2 | RTX 4090 | 120s"
```

## Vast.ai Instance Lifecycle

- **`stop` preserves disk** — installed packages, models, patches survive. Relaunch in ~30s.
- **`destroy` loses everything** — must reinstall from scratch (~15 min).
- **New instances need `attach ssh`** — even if key is on account, each instance needs explicit attachment.
- **Instance stuck in "created"** — `vastai start instance <ID>` explicitly, or destroy and recreate.
- **Save patches as scripts** — upload `patch_trellis2.py` alongside setup script for reproducibility.

## Setup Script Pitfall — Working Directory

The `setup.sh` runs `cd TRELLIS.2` internally, but subsequent commands in the same bash script may not be in that directory. Always use **absolute paths** for Python patching commands after `setup.sh`:

```bash
# WRONG — relative path fails after setup.sh changes directory
. ./setup.sh --basic ...
python3 -c "import json; cfg = json.load(open('pretrained/pipeline.json'))"

# CORRECT — absolute paths
. ./setup.sh --basic ...
python3 -c "import json; cfg = json.load(open('/root/TRELLIS.2/pretrained/pipeline.json'))"
```

Or explicitly `cd /root/TRELLIS.2` before each Python block.

## JPEG Input Without Alpha

When input is a JPEG (no alpha channel), converting to RGBA sets alpha=255 everywhere. The `preprocess_image` method checks `if not np.all(alpha == 255)` — this evaluates to `False` for JPEGs, so `has_alpha=False`. With rembg_model=None (patched), the code falls through to `output = input.convert('RGBA')`, which works correctly. No special handling needed.

## Tested Configs

| Offer ID | GPU | $/hr | Location | Notes |
|---|---|---|---|---|
| 37064190 | RTX 4090 | $0.67 | Iceland | 32 vCPUs, 72GB RAM |
| 37080124 | RTX 4090 | $0.64 | Norway | 16 vCPUs, 64GB RAM |

## Cost Comparison

| GPU | $/hr | 1024³ time | Cost per asset |
|---|---|---|---|
| RTX 4090 | $0.40-0.67 | **52.8s** (measured) | ~$0.01 |
| H200 | $4.00 | ~17s | ~$0.02 |

For batches < 50 assets: RTX 4090 wins on cost. For speed: H200 wins 3x wall-clock.
