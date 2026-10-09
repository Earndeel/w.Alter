#!/usr/bin/env python3
"""
Automated TRELLIS.2 patcher — applies all 3 required patches for:
1. DINOv3 architecture fix (model.layer → model.model.layer)
2. rembg_model config (set to null)
3. rembg_model loading + preprocessing code (None handling)

Run AFTER git clone + setup.sh, BEFORE first generation.

Usage:
  python3 patch_trellis2.py [--repo /path/to/TRELLIS.2] [--download-model]

--download-model: Also download full model repo locally (for from_pretrained local path)
"""
import argparse
import os
import sys


def patch_dinov3(trellis_dir):
    """Fix DINOv3 model.layer → model.model.layer"""
    path = os.path.join(trellis_dir, "trellis2/modules/image_feature_extractor.py")
    with open(path) as f:
        content = f.read()

    old = "for i, layer_module in enumerate(self.model.layer):"
    new = "for i, layer_module in enumerate(self.model.model.layer):"

    if old in content:
        content = content.replace(old, new)
        with open(path, "w") as f:
            f.write(content)
        print("✅ Patched DINOv3 model.layer → model.model.layer")
    else:
        print("⏭️  DINOv3 patch already applied or pattern not found")


def patch_rembg_loading(trellis_dir):
    """Patch from_pretrained loading to handle None rembg_model"""
    path = os.path.join(trellis_dir, "trellis2/pipelines/trellis2_image_to_3d.py")
    with open(path) as f:
        content = f.read()

    old = "pipeline.rembg_model = getattr(rembg, args['rembg_model']['name'])(**args['rembg_model']['args'])"
    new = """if args.get('rembg_model') is not None:
            pipeline.rembg_model = getattr(rembg, args['rembg_model']['name'])(**args['rembg_model']['args'])
        else:
            pipeline.rembg_model = None"""

    if old in content:
        content = content.replace(old, new)
        with open(path, "w") as f:
            f.write(content)
        print("✅ Patched rembg_model loading (None handling)")
    else:
        print("⏭️  rembg loading patch already applied or pattern not found")


def patch_rembg_preprocess(trellis_dir):
    """Patch preprocess_image to skip rembg when model is None"""
    path = os.path.join(trellis_dir, "trellis2/pipelines/trellis2_image_to_3d.py")
    with open(path) as f:
        content = f.read()

    old = """        if has_alpha:
            output = input
        else:
            input = input.convert('RGB')
            if self.low_vram:
                self.rembg_model.to(self.device)
            output = self.rembg_model(input)
            if self.low_vram:
                self.rembg_model.cpu()"""

    new = """        if has_alpha:
            output = input
        elif self.rembg_model is not None:
            input = input.convert('RGB')
            if self.low_vram:
                self.rembg_model.to(self.device)
            output = self.rembg_model(input)
            if self.low_vram:
                self.rembg_model.cpu()
        else:
            output = input.convert('RGBA')"""

    if old in content:
        content = content.replace(old, new)
        with open(path, "w") as f:
            f.write(content)
        print("✅ Patched preprocess_image (rembg None bypass)")
    else:
        print("⏭️  rembg preprocess patch already applied or pattern not found")


def patch_config(model_dir):
    """Set rembg_model to null in pipeline.json"""
    path = os.path.join(model_dir, "pipeline.json")
    if not os.path.exists(path):
        print(f"⏭️  Config not found at {path} — skipping config patch")
        return

    import json
    with open(path) as f:
        cfg = json.load(f)

    if cfg.get("args", {}).get("rembg_model") is not None:
        cfg["args"]["rembg_model"] = None
        with open(path, "w") as f:
            json.dump(cfg, f, indent=4)
        print(f"✅ Patched config: rembg_model → null ({path})")
    else:
        print("⏭️  Config already has rembg_model=null")


def download_model(model_dir):
    """Download full TRELLIS.2-4B model repo for local from_pretrained"""
    if os.path.exists(os.path.join(model_dir, "pipeline.json")):
        print(f"⏭️  Model already at {model_dir}")
        return

    from huggingface_hub import snapshot_download
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        print("❌ HF_TOKEN not set — cannot download gated model")
        sys.exit(1)

    print(f"📥 Downloading microsoft/TRELLIS.2-4B to {model_dir}...")
    snapshot_download("microsoft/TRELLIS.2-4B", local_dir=model_dir, token=token)
    print(f"✅ Model downloaded to {model_dir}")


def main():
    parser = argparse.ArgumentParser(description="Patch TRELLIS.2 for Vast.ai deployment")
    parser.add_argument("--repo", default="/root/TRELLIS.2", help="TRELLIS.2 repo path")
    parser.add_argument("--model-dir", default=None, help="Model dir (default: <repo>/pretrained or /root/TRELLIS.2-4B)")
    parser.add_argument("--download-model", action="store_true", help="Download full model repo locally")
    args = parser.parse_args()

    trellis_dir = args.repo
    model_dir = args.model_dir or os.path.join(trellis_dir, "pretrained")

    if not os.path.isdir(trellis_dir):
        print(f"❌ TRELLIS.2 not found at {trellis_dir}")
        sys.exit(1)

    print(f"🔧 Patching TRELLIS.2 at {trellis_dir}")

    # Always apply code patches
    patch_dinov3(trellis_dir)
    patch_rembg_loading(trellis_dir)
    patch_rembg_preprocess(trellis_dir)

    # Download model if requested
    if args.download_model:
        model_dir = args.model_dir or "/root/TRELLIS.2-4B"
        download_model(model_dir)

    # Patch config
    patch_config(model_dir)

    print("\n✅ All patches applied! Ready to generate.")
    print(f"   Use: Trellis2ImageTo3DPipeline.from_pretrained('{model_dir}')")


if __name__ == "__main__":
    main()
