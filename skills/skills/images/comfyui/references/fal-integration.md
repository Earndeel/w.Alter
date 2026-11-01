# Fal.ai Integration for CPU-Only ComfyUI

When ComfyUI runs on a machine without GPU (headless server, CI, ARM64 cloud instance),
local image/video generation is unusable (10-30 min/image). The solution is to install
Fal.ai custom nodes that replace local compute nodes with API calls to Fal.ai's GPU fleet.

## Nodes Available

Install these two complementary custom nodes into `custom_nodes/`:

| Node Pack | Repo | What it provides |
|-----------|------|-----------------|
| `ComfyUI-fal-API` | `gokayfem/ComfyUI-fal-API` | Image, video, LLM, VLM, trainer, upscaler nodes (Sana, Flux, Recraft, etc.) |
| `ComfyUI-fal-Connector` | `badayvedat/ComfyUI-fal-Connector` | Bridge to run *any* ComfyUI workflow on Fal.ai's hosted Comfy Server |

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/gokayfem/ComfyUI-fal-API.git
git clone https://github.com/badayvedat/ComfyUI-fal-Connector.git
cd ..
source .venv/bin/activate
pip install fal-client fal httpx httpx-sse opencv-python
```

## Credential Setup

Fal.ai key must be set in **both** config files AND the systemd service env:

```bash
FAL_KEY="fal_live_..."

# Node 1: ComfyUI-fal-API
cat > custom_nodes/ComfyUI-fal-API/config.ini << EOF
[API]
FAL_KEY = ${FAL_KEY}
EOF

# Node 2: ComfyUI-fal-Connector
cat > custom_nodes/ComfyUI-fal-Connector/fal-config.ini << EOF
[fal]
application_name = fal-ai/comfy-server/stream
api_key = ${FAL_KEY}

[huggingface]
token =
EOF

# Systemd service must also export FAL_KEY
# Environment=FAL_KEY=${FAL_KEY}
```

The `FAL_KEY` env var is checked first by `fal_client`; the config.ini files
are fallbacks used by the custom node internals.

## Key Classes (from ComfyUI-fal-API)

### Image Generation

```python
NODE_CLASS_MAPPINGS = {
    "Sana_fal": Sana,                    # fast image gen
    "FluxPro_fal": FluxPro,              # high quality
    "FluxDev_fal": FluxDev,
    "FluxSchnell_fal": FluxSchnell,
    "FluxLora_fal": FluxLora,
    "Recraft_fal": Recraft,
    "Ideogramv3_fal": Ideogramv3,
    "Hidreamfull_fal": HidreamFull,
    "QwenImageEdit_fal": QwenImageEdit,
    "SeedEditV3_fal": SeedEditV3,
}
```

### Video Generation

```python
NODE_CLASS_MAPPINGS = {
    "Kling_fal": KlingNode,              # Kling text/image-to-video
    "SeedanceTextToVideo_fal": SeedanceTextToVideo,  # Seedance T2V
    "SeedanceProImageToVideo_fal": SeedanceProImageToVideo,
    "CombinedVideoGeneration_fal": CombinedVideoGeneration,
    # Also in the same pack: Wan, Hunyuan, LTXV, Runway, Pixverse nodes
}
```

Video nodes return `STRING` (a download URL), not `VIDEO` tensor. See
"Output Type Mismatch" below.

## Example: Sana txt2img via REST API

```python
import json, urllib.request

workflow = {
    "1": {
        "class_type": "Sana_fal",
        "inputs": {
            "prompt": "a majestic lion in a savanna at golden hour",
            "negative_prompt": "blurry, low quality",
            "image_size": "square_hd",
            "width": 1024, "height": 1024,
            "num_inference_steps": 20,
            "guidance_scale": 5.0,
            "num_images": 1,
            "seed": 42,
            "enable_safety_checker": True,
            "output_format": "png"
        }
    },
    "2": {
        "class_type": "SaveImage",
        "inputs": {
            "images": ["1", 0],
            "filename_prefix": "fal_sana_output"
        }
    }
}

payload = json.dumps({"prompt": workflow}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8188/api/prompt",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST"
)
with urllib.request.urlopen(req, timeout=10) as resp:
    result = json.loads(resp.read())
    print(result["prompt_id"])   # poll /api/history/<id> for completion
```

## Execution Flow

1. Workflow JSON submitted to local ComfyUI via `POST /api/prompt`
2. Local ComfyUI parses the graph, reaches `Sana_fal` node
3. `Sana_fal` calls `fal_client.run("fal-ai/sana", arguments={...})`
4. Fal.ai GPU fleet generates the image (~5-40s depending on model)
5. Result URL downloaded by the node, passed to downstream nodes (SaveImage, etc.)
6. Final output saved to `ComfyUI/output/` as if it were local

The user only interacts with ComfyUI's standard API — no Fal.ai-specific API
calls needed on the client side.

## Verification

```bash
# Check nodes loaded
curl -s http://127.0.0.1:8188/api/object_info/Sana_fal | python3 -m json.tool

# Check history for a completed job
curl -s http://127.0.0.1:8188/api/history/<prompt_id> | python3 -c "
import sys, json
d = json.load(sys.stdin)
for k,v in d.items():
    print('status:', v.get('status',{}).get('status_str'))
    print('outputs:', json.dumps(v.get('outputs',{}), indent=2))
"
```

## Pitfalls

- **`fal_client.auth.MissingCredentialsError`** — FAL_KEY is not in env AND
  not in config.ini. Set it in both places and restart the ComfyUI service.
- **cv2 import error** — `opencv-python` must be installed in the venv, not
  system-wide. `pip install opencv-python` from inside `.venv`.
- **Port 8188 already in use** — `comfy launch --background` from uvx cache
  may leave a zombie process. Kill it with `ps aux | grep comfy` then restart.
- **SaveImage truncates filename** — long prefixes get shortened by ComfyUI
  internally. Use short `filename_prefix` values (<20 chars).
- **Fal.ai rate limits** — free tier has limits; if jobs queue for >2 min,
  the node may timeout. Use `run_workflow.py --timeout 120` or bump systemd
  timeout.
