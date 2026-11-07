---
name: free-gpu-stack
description: "Vast.ai GPU provisioning — search offers, create/destroy instances, templates, cost optimization, pre-built environments. Use for on-demand GPU workloads (TRELLIS, inference, training)."
version: 1.0.0
tags: [gpu, vastai, cloud, trellis, 3d, inference, cuda]
---

# Vast.ai GPU Workflow

On-demand GPU provisioning via `vastai` CLI. Pre-configured for cost-efficient, fast spin-up/down cycles.

## Prerequisites

- `vastai` CLI installed and configured (API key in `~/.config/vastai/vast_api_key`)
- Vault credential: `vastai/api_key`
- User ID: 347995

## Cost Model

| Resource | Cost |
|----------|------|
| RTX 4090 compute | ~$0.65-0.71/hr |
| Storage (stopped instance) | ~$0.04-0.05/hr per 100GB disk |
| **Destroyed instance** | **$0.00** |

**RULE**: Always destroy instances when done. Stopped instances still incur storage charges.

## Lifecycle Commands

```bash
# Search available GPUs (RTX 4090 recommended for most workloads)
vastai search offers 'gpu_name=RTX_4090' --raw

# Create instance from template or image
vastai create instance OFFER_ID --image pytorch/pytorch:2.4.0-cuda12.4-cudnn9-devel --disk 100 --ssh

# Create from template (instant setup)
vastai create instance OFFER_ID --template TEMPLATE_ID

# Check running instances
vastai show instances --raw

# Stop (still charges storage)
vastai stop instance INSTANCE_ID

# Destroy (zero charges)
echo "y" | vastai destroy instance INSTANCE_ID

# Get SSH connection info
vastai ssh-url INSTANCE_ID
```

## Template System

Templates = pre-configured environments for instant deployment.

### Create a template from running instance

```bash
# Snapshot a running container to Docker Hub
vastai take snapshot INSTANCE_ID \
  --repo dockerhub_username/image-name \
  --docker_login_user USER \
  --docker_login_pass PASS

# Then create template pointing to that image
vastai create template \
  --name "trellis-ready" \
  --image dockerhub_username/image-name:latest \
  --ssh \
  --onstart-cmd "#!/bin/bash\ncd /workspace && conda activate trellis" \
  --disk_space 100
```

### Template with onstart script (no Docker Hub needed)

```bash
vastai create template \
  --name "trellis-env" \
  --image pytorch/pytorch:2.4.0-cuda12.4-cudnn9-devel \
  --ssh \
  --onstart-cmd '#!/bin/bash
set -e
if [ ! -d /workspace/TRELLIS ]; then
  cd /workspace
  git clone --recurse-submodules https://github.com/microsoft/TRELLIS.git
  cd TRELLIS
  . ./setup.sh --new-env --basic --xformers --flash-attn --diffoctreerast --spconv --mipgaussian --kaolin --nvdiffrast
fi
conda activate trellis
echo "TRELLIS ready"' \
  --disk_space 100
```

### List user templates

```bash
vastai search templates --raw | python3 -c "
import sys,json
data=json.loads(sys.stdin.read())
for t in data:
    if t.get('creator_id') == 347995:
        print(f\"{t.get('id')} | {t.get('desc')} | {t.get('image')}\")
"
```

## TRELLIS 3D Generation

### Recommended GPU

- **RTX 4090** (24GB VRAM) — sweet spot, ~$0.65/hr
- H100/H200 = overkill for TRELLIS (model is 2B-4B params, needs 16GB+ VRAM)

### Key parameters (pipeline.run)

```python
outputs = pipeline.run(
    image,
    seed=42,                                    # Change for variation
    sparse_structure_sampler_params={
        "steps": 20,                            # Default: 12, ↑ = better geometry
        "cfg_strength": 7.5,                    # Default: 7.5, ↑ = more faithful to input
    },
    slat_sampler_params={
        "steps": 20,                            # Default: 12, ↑ = better texture
        "cfg_strength": 5,                      # Default: 3, ↑ = more detailed texture
    },
)

# GLB export — quality knobs
glb = postprocessing_utils.to_glb(
    outputs['gaussian'][0],
    outputs['mesh'][0],
    simplify=0.8,          # Default: 0.95 (removes 95% triangles). 0.8 = keep more detail
    texture_size=2048,     # Default: 1024. 2048 = sharper textures
)
```

### Pipeline: Image → 3D → GLB → Telegram

1. Generate image via GPT Image / ERNIE (clean, white background, single object)
2. Upload to Vast.ai instance via SCP
3. Run TRELLIS inference with tuned parameters
4. Download GLB via SCP
5. Send to Telegram

### Quality checklist for input images

- White/neutral background
- Single object, centered
- Good lighting, no shadows on object
- Resolution: 512×512 to 1024×1024
- For puttgame assets: side/front view, clean edges

## Cost Optimization Rules

1. **Never leave instances running unattended** — destroy when task complete
2. **Use templates** — reduces setup from 15min to 0min on re-launch
3. **Disk = money** — use minimum disk needed (50GB for inference, 100GB for training)
4. **Spot instances** — use `--onstart-cmd` to handle interruptions gracefully
5. **Pre-download models** — bake HuggingFace model downloads into template onstart

## Pitfalls

- `vastai destroy` requires confirmation — pipe `echo "y"` or use `--raw` flag
- `show instances` deprecated — use `show instances-v1` for new CLI
- SSH key must be added: `vastai create ssh-key ~/.ssh/id_ed25519.pub`
- CUDA version in image must match GPU compute capability (RTX 4090 = 8.9, needs CUDA 11.8+)
- Conda activate doesn't work in non-interactive onstart scripts — use `source activate trellis` or full path
