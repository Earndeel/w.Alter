#!/usr/bin/env python3
"""One bounded, non-explicit Qwen-Image 2.1 GGUF test inside a Colab notebook.

Colab cell: !python /content/runtime_inference.py
No server, tunnel, remote worker, keep-alive, paid API, fallback model or LoRA.
This file is import-safe for offline contract tests; GPU code is lazy-imported.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request

MODEL_REPO = "abenzerps/Qwen-Image-2.1-Uncensored-GGUF"
MODEL_REVISION = "6b34e59458d3eb7ba6a6f86a116aed5253dc02c3"
COMFY_REVISION = "7f7fd918ed0815c5d5ef2ccfe44bfc8e72cfd217"
GGUF_REVISION = "373048b8403a7820620065210a691263d4da0a61"
TEMPLATE_REVISION = "00309dce76e9c4f436dc85144d39eccc863fb304"
TEMPLATE_PATH = "templates/image_qwen_image_2_1_t2i.json"
TEMPLATE_SHA256 = "5f2b50eeaf27e56a45456681ad5319df1ae51243d9653ac3f92c7dc05d1e1503"
MODEL_FILES = [
    {"repo_path": "qwen-image-2.1-UC-Q4_K_M.gguf",
     "local_path": "diffusion_models/qwen-image-2.1-UC-Q4_K_M.gguf",
     "size": 4604558112,
     "sha256": "e79c8a009f2ecbdb6c70fd663d9aea9ee304a0d91f347e4169a756b8ad141b41"},
    {"repo_path": "text_encoders/qwen3vl_8b_int8_convrot.safetensors",
     "local_path": "text_encoders/qwen3vl_8b_int8_convrot.safetensors",
     "size": 9350798360,
     "sha256": "8bfd0f6e12abf2d2d697ecc888e5e90b0d6741d6708f05799f53afa560452e8f"},
    {"repo_path": "vae/qwen_image_2.1_vae_bf16.safetensors",
     "local_path": "vae/qwen_image_2.1_vae_bf16.safetensors",
     "size": 675509688,
     "sha256": "bb21f7473051e1ac368515dd3f2e15cd44d7a11748ee8823e1ddca3e4876b7c9"},
]
PROMPT = "editorial fashion photograph of a clearly adult 30-year-old woman wearing opaque black lace lingerie and an open silk robe, standing confidently beside a rain-streaked window in an elegant Parisian hotel, tasteful boudoir fashion photography, soft cinematic light, realistic skin texture, fully covered breasts and pelvis, no nudity, no sexual activity"
NEGATIVE_PROMPT = "nude, exposed nipples, exposed genitals, sexual acts, child, teenager, young-looking, watermark, text"
WIDTH, HEIGHT, STEPS, SEED, BATCH_SIZE = 1024, 1024, 25, 42, 1
# Official template CFG=1 skips negative guidance; 2 makes the supplied negative
# prompt active. This documented deviation may over-sharpen edges.
CFG = 2.0
CONTENT = Path("/content")
WORK = CONTENT / "walter-qwen-image-test"
COMFY = WORK / "ComfyUI"
GGUF_DIR = COMFY / "custom_nodes" / "ComfyUI-GGUF"
OUTPUT_PNG = CONTENT / "walter-qwen-image-test.png"
RESULT_JSON = CONTENT / "walter-qwen-image-result.json"
COMFY_FLAGS = ["--disable-dynamic-vram", "--disable-async-offload",
               "--reserve-vram", "2", "--use-pytorch-cross-attention",
               "--bf16-unet", "--bf16-text-enc", "--bf16-vae",
               "--preview-method", "none", "--offline"]


class TestAbort(RuntimeError):
    """Safe-to-report error messages authored here, never third-party payloads."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(path: Path, spec: dict) -> dict:
    if not path.is_file() or path.stat().st_size != spec["size"]:
        raise TestAbort("Model file missing or byte count differs from the pinned manifest")
    digest = sha256_file(path)
    if digest != spec["sha256"]:
        raise TestAbort("Model SHA256 mismatch; no inference performed with this file")
    return {"path": str(path), "size_bytes": path.stat().st_size, "sha256": digest}


def atomic_json(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def inspect_template(raw: bytes) -> dict:
    if hashlib.sha256(raw).hexdigest() != TEMPLATE_SHA256:
        raise TestAbort("Official template hash changed; refusing unreviewed workflow")
    template = json.loads(raw)
    inner_nodes = [n for graph in template["definitions"]["subgraphs"] for n in graph["nodes"]]
    kinds = sorted({n["type"] for n in inner_nodes})
    required = {"UNETLoader", "CLIPLoader", "VAELoader", "TextEncodeQwenImage21", "KSampler", "VAEDecode"}
    if not required.issubset(kinds):
        raise TestAbort("Pinned official template lacks required Qwen Image 2.1 nodes")
    values = next(n["widgets_values"] for n in inner_nodes if n["type"] == "KSampler")
    settings = dict(zip(["steps", "cfg", "sampler_name", "scheduler", "denoise"], values[2:]))
    if settings != {"steps": 25, "cfg": 1, "sampler_name": "euler", "scheduler": "simple", "denoise": 1}:
        raise TestAbort("Unexpected published template sampler settings")
    return {"sha256": TEMPLATE_SHA256, "revision": TEMPLATE_REVISION,
            "path": TEMPLATE_PATH, "sampler": settings, "node_types": kinds}


def require_colab() -> None:
    try:
        is_colab = importlib.util.find_spec("google.colab") is not None
    except (ModuleNotFoundError, ValueError):
        is_colab = False
    if not is_colab or not CONTENT.is_dir() or platform.system() != "Linux" or platform.machine() != "x86_64":
        raise TestAbort("Execution is restricted to an interactive Linux x86_64 Google Colab runtime; no VM installation or inference")


def request_manifest() -> dict:
    return {"model_repository": MODEL_REPO, "model_revision": MODEL_REVISION,
            "model_files": MODEL_FILES,
            "code_revisions": {"comfyui": COMFY_REVISION, "gguf": GGUF_REVISION,
                               "workflow_templates": TEMPLATE_REVISION},
            "parameters": {"prompt": PROMPT, "negative_prompt": NEGATIVE_PROMPT,
                           "width": WIDTH, "height": HEIGHT, "batch_size": BATCH_SIZE,
                           "steps": STEPS, "seed": SEED, "cfg": CFG,
                           "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0},
            "outputs": {"png": str(OUTPUT_PNG), "json": str(RESULT_JSON)},
            "content_review_required": True,
            "workflow_deviations": [
                "UC-Q4_K_M GGUF replaces only the diffusion loader; no LoRA applied",
                "CFG=2 activates the requested negative prompt (official template CFG=1 ignores it)",
                "No prompt enhancement: preserve the exact safe prompt and avoid an extra model",
                "Use native TextEncodeQwenImage21 latent output (64 channels, spatial compression 16)",
                "Lossless prefix KV cache on CPU, sequential model offload, tiled VAE decode"],
            "comfy_flags": COMFY_FLAGS}


def command(argv: list[str], *, cwd: Path | None = None, log: Path | None = None,
            timeout: int = 1800) -> str:
    require_colab()
    if log is not None:
        with log.open("a", encoding="utf-8") as handle:
            result = subprocess.run(argv, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT,
                                    text=True, timeout=timeout)
        output = ""
    else:
        result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        output = result.stdout
    if result.returncode:
        raise TestAbort(f"Public setup command failed with exit code {result.returncode}; inspect its local setup log")
    return output


def nvidia_info() -> str | None:
    if shutil.which("nvidia-smi") is None:
        return None
    return command(["nvidia-smi", "--query-gpu=name,uuid,memory.total,memory.free,driver_version",
                    "--format=csv,noheader,nounits"], timeout=30).strip()


def preflight(report: dict) -> dict:
    require_colab()
    # Import CUDA in a fresh process before pip, not in the notebook kernel.
    probe = (
        "import json, torch; import importlib.metadata as md; "
        "available=torch.cuda.is_available(); "
        "p=torch.cuda.get_device_properties(0) if available else None; "
        "f,t=torch.cuda.mem_get_info(0) if available else (0,0); "
        "print(json.dumps({'cuda_available':available,'name':p.name if p else None,"
        "'total_bytes':t,'free_bytes':f,'compute_capability':[p.major,p.minor] if p else None,"
        "'torch_cuda':torch.version.cuda,"
        "'framework_packages':{k:md.version(k) for k in ['torch','torchvision']}}))"
    )
    info = json.loads(command([sys.executable, "-c", probe], timeout=120))
    report["gpu"] = {**info, "nvidia_smi_before": nvidia_info()}
    if not info["cuda_available"]:
        raise TestAbort("No CUDA GPU assigned to this Colab notebook; no install or model download started")
    versions = info["framework_packages"]
    match = re.match(r"(\d+)\.(\d+)", versions["torch"])
    if not match or tuple(map(int, match.groups())) < (2, 8):
        raise TestAbort("This preparation requires Colab's CUDA torch >=2.8; it does not replace the supplied framework")
    if info["compute_capability"][0] < 8:
        raise TestAbort("Native BF16 GPU required (Ampere or newer); this script does not silently switch models or precision")
    if info["total_bytes"] < 16 * 2**30 or info["free_bytes"] < 12 * 2**30:
        raise TestAbort("Conservative guard: at least 16 GiB GPU memory and 12 GiB free VRAM required")
    mem = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        parts = line.split()
        if parts[0] in {"MemTotal:", "MemAvailable:"}:
            mem[parts[0].rstrip(":")] = int(parts[1]) * 1024
    report["host"] = {"python": platform.python_version(), "machine": platform.machine(),
                      "ram_bytes": mem, "disk_free_bytes": shutil.disk_usage(CONTENT).free}
    if mem.get("MemAvailable", 0) < 12 * 2**30:
        raise TestAbort("Conservative guard: at least 12 GiB available host RAM required for the 8B encoder/offload")
    return versions


def ensure_repository(path: Path, url: str, revision: str, *, skip_setup: bool) -> None:
    require_colab()
    git = ["git", "-c", "credential.helper=", "-c", "core.askPass=", "-c", "http.extraHeader="]
    log = WORK / "git-setup.log"
    if not (path / ".git").is_dir():
        if skip_setup or path.exists():
            raise TestAbort("Pinned code checkout missing, or target already exists without git metadata")
        path.parent.mkdir(parents=True, exist_ok=True)
        command(git + ["init", str(path)], log=log)
        command(git + ["remote", "add", "origin", url], cwd=path, log=log)
        command(git + ["fetch", "--depth", "1", "origin", revision], cwd=path, log=log)
        command(git + ["checkout", "--detach", "FETCH_HEAD"], cwd=path, log=log)
    actual = command(git + ["rev-parse", "HEAD"], cwd=path).strip()
    origin = command(git + ["remote", "get-url", "origin"], cwd=path).strip()
    dirty = command(git + ["status", "--porcelain", "--untracked-files=no"], cwd=path).strip()
    if actual != revision or origin != url or dirty:
        raise TestAbort("Code checkout differs from the inspected immutable revision; refusing to overwrite it")


def setup_dependencies(framework: dict, *, skip_setup: bool) -> None:
    require_colab()
    ensure_repository(COMFY, "https://github.com/Comfy-Org/ComfyUI.git", COMFY_REVISION,
                      skip_setup=skip_setup)
    ensure_repository(GGUF_DIR, "https://github.com/leejet/ComfyUI-GGUF.git", GGUF_REVISION,
                      skip_setup=skip_setup)
    if skip_setup:
        return
    constraints = WORK / "preserve-colab-framework.txt"
    constraints.write_text("\n".join(f"{name}=={version}" for name, version in framework.items()) + "\n")
    command([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
             "--no-input", "--constraint", str(constraints),
             "-r", str(COMFY / "requirements.txt"), "-r", str(GGUF_DIR / "requirements.txt"),
             "gguf==0.19.0", "transformers==4.57.1", "huggingface-hub==0.36.0", "safetensors==0.7.0"],
            log=WORK / "pip-setup.log", timeout=1800)


def load_nodes():
    require_colab()
    if "comfy.cli_args" in sys.modules or "nodes" in sys.modules:
        raise TestAbort("ComfyUI already imported; launch this script using !python in a fresh notebook process")
    sys.path.insert(0, str(COMFY))
    previous_argv = sys.argv[:]
    try:
        import comfy.options
        comfy.options.enable_args_parsing()
        import torch
        flags = COMFY_FLAGS[:]
        # Keep the same conservative budget even if Colab assigns an 80 GiB GPU.
        reserve = max(2.0, torch.cuda.get_device_properties(0).total_memory / 2**30 - 38.0)
        flags[flags.index("--reserve-vram") + 1] = str(reserve)
        sys.argv = [str(Path(__file__).resolve()), *flags]
        import comfy.cli_args
    finally:
        sys.argv = previous_argv
    import nodes
    from comfy_extras.nodes_qwen import TextEncodeQwenImage21, QwenImage21Cache
    spec = importlib.util.spec_from_file_location(
        "walter_comfy_gguf", GGUF_DIR / "__init__.py", submodule_search_locations=[str(GGUF_DIR)])
    package = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = package
    spec.loader.exec_module(package)
    # GGUF loader uses the legacy "unet" alias, which ComfyUI maps to diffusion_models.
    import folder_paths
    folder_paths.add_model_folder_path("diffusion_models", str(COMFY / "models" / "diffusion_models"))
    folder_paths.add_model_folder_path("text_encoders", str(COMFY / "models" / "text_encoders"))
    folder_paths.add_model_folder_path("vae", str(COMFY / "models" / "vae"))
    if "UnetLoaderGGUF" not in package.NODE_CLASS_MAPPINGS:
        raise TestAbort("Inspected GGUF loader node not present")
    return nodes, TextEncodeQwenImage21, QwenImage21Cache, package.NODE_CLASS_MAPPINGS["UnetLoaderGGUF"]


def prepare_models(report: dict, *, skip_setup: bool) -> None:
    require_colab()
    from huggingface_hub import HfApi, hf_hub_download
    # Explicit token=False: public access only; never read a cached HF credential.
    metadata = HfApi().model_info(MODEL_REPO, revision=MODEL_REVISION,
                                 files_metadata=True, token=False)
    if metadata.sha != MODEL_REVISION:
        raise TestAbort("Hugging Face returned a different model revision")
    siblings = {s.rfilename: s for s in metadata.siblings}
    for item in MODEL_FILES:
        sibling = siblings.get(item["repo_path"])
        if sibling is None or sibling.lfs is None or sibling.size != item["size"] or sibling.lfs.sha256 != item["sha256"]:
            raise TestAbort("Public model metadata differs from the independently recorded manifest")
    report["model_files_verified"] = []
    for item in MODEL_FILES:
        destination = COMFY / "models" / item["local_path"]
        if not destination.is_file():
            if skip_setup:
                raise TestAbort("Model file missing with --skip-setup; no model substitution allowed")
            print(f"Downloading public file: {item['repo_path']}", flush=True)
            downloaded = Path(hf_hub_download(repo_id=MODEL_REPO, filename=item["repo_path"],
                              revision=MODEL_REVISION, local_dir=WORK / "downloads", token=False))
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_symlink():
                destination.unlink()  # only repair a broken link at this dedicated target
            destination.symlink_to(downloaded.resolve())
        result = verify_file(destination, item)
        report["model_files_verified"].append({**result, "repo_path": item["repo_path"],
                                               "revision": MODEL_REVISION})
        atomic_json(RESULT_JSON, report)
    template_url = f"https://raw.githubusercontent.com/Comfy-Org/workflow_templates/{TEMPLATE_REVISION}/{TEMPLATE_PATH}"
    raw = urllib.request.urlopen(template_url, timeout=60).read(2 * 1024 * 1024)
    report["official_template"] = inspect_template(raw)
    (WORK / "official-t2i-template.json").write_bytes(raw)


@contextmanager
def phase(report: dict, name: str, *, cuda: bool = False):
    report["stage"] = name
    atomic_json(RESULT_JSON, report)
    print(f"Stage: {name}", flush=True)
    torch = sys.modules.get("torch")
    if cuda:
        torch.cuda.synchronize()
    start = time.perf_counter()
    try:
        yield
    finally:
        if cuda:
            torch.cuda.synchronize()
        report.setdefault("timings_seconds", {})[name] = round(time.perf_counter() - start, 4)
        if cuda:
            report["gpu"]["torch_peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
            report["gpu"]["torch_peak_reserved_bytes"] = torch.cuda.max_memory_reserved()
        atomic_json(RESULT_JSON, report)


def offload_and_collect(mm) -> None:
    mm.unload_all_models()
    gc.collect()
    mm.cleanup_models()
    mm.soft_empty_cache()


def execute_inference(report: dict, node_bundle=None) -> None:
    require_colab()
    if node_bundle is None:
        node_bundle = load_nodes()
    import torch
    import comfy.model_management as mm
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo
    nodes, TextEncodeQwenImage21, QwenImage21Cache, UnetLoaderGGUF = node_bundle
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    torch.cuda.reset_peak_memory_stats()
    try:
        with torch.inference_mode():
            with phase(report, "text_encode", cuda=True):
                clip = nodes.CLIPLoader().load_clip(
                    clip_name=Path(MODEL_FILES[1]["repo_path"]).name, type="qwen_image", device="default")[0]
                if clip.tokenizer.__class__.__name__ != "QwenImage21Tokenizer":
                    raise TestAbort("Wrong text encoder family detected; expected native Qwen Image 2.1")
                report["encoder"] = {"tokenizer": clip.tokenizer.__class__.__name__,
                                     "load_device": str(clip.patcher.load_device),
                                     "offload_device": str(clip.patcher.offload_device)}
                positive, negative, latent = TextEncodeQwenImage21.execute(
                    clip=clip, prompt=PROMPT, negative_prompt=NEGATIVE_PROMPT,
                    resolution=WIDTH, images={}).result
                if tuple(latent["samples"].shape) != (1, 64, HEIGHT // 16, WIDTH // 16):
                    raise TestAbort("Unexpected Qwen Image 2.1 latent geometry")
                report["latent_shape"] = list(latent["samples"].shape)
            offload_and_collect(mm)
            del clip
            offload_and_collect(mm)
            with phase(report, "diffusion_load", cuda=True):
                model = UnetLoaderGGUF().load_unet(
                    unet_name=MODEL_FILES[0]["repo_path"], dequant_dtype="bfloat16",
                    patch_dtype="default", patch_on_device=False)[0]
                architecture = model.model.model_config.unet_config.get("image_model")
                if architecture != "qwen_image21":
                    raise TestAbort("Wrong diffusion architecture; expected qwen_image21, never old Qwen-Image")
                report["diffusion"] = {"architecture": architecture, "load_device": str(model.load_device),
                                       "offload_device": str(model.offload_device)}
                model = QwenImage21Cache.execute(model=model, device="cpu", dtype="default").result[0]
            with phase(report, "sampling", cuda=True):
                sampled = nodes.KSampler().sample(
                    model=model, seed=SEED, steps=STEPS, cfg=CFG,
                    sampler_name="euler", scheduler="simple",
                    positive=positive, negative=negative, latent_image=latent, denoise=1.0)[0]
            offload_and_collect(mm)
            del model, positive, negative, latent
            offload_and_collect(mm)
            with phase(report, "vae_decode", cuda=True):
                vae = nodes.VAELoader().load_vae(vae_name=Path(MODEL_FILES[2]["repo_path"]).name)[0]
                pixels = nodes.VAEDecodeTiled().decode(
                    vae=vae, samples=sampled, tile_size=512, overlap=64)[0]
                if pixels.shape[0] != 1 or tuple(pixels.shape[1:3]) != (HEIGHT, WIDTH) or pixels.shape[-1] not in (3, 4):
                    raise TestAbort("Decoder did not produce exactly one requested-resolution RGB/RGBA image")
                if not torch.isfinite(pixels).all().item():
                    raise TestAbort("Non-finite decoder output; not exporting an invalid image")
                image_array = pixels[0].detach().float().clamp(0, 1).mul(255).round().to(torch.uint8).cpu().numpy()
            offload_and_collect(mm)
            del vae, sampled, pixels
            offload_and_collect(mm)
            with phase(report, "export_png"):
                png_meta = PngInfo()
                png_meta.add_text("walter_test", json.dumps(request_manifest(), ensure_ascii=False))
                image = Image.fromarray(image_array)
                temporary = OUTPUT_PNG.with_suffix(".png.tmp")
                image.save(temporary, format="PNG", pnginfo=png_meta)
                with Image.open(temporary) as check:
                    check.verify()
                temporary.replace(OUTPUT_PNG)
                report["output"] = {"path": str(OUTPUT_PNG), "sha256": sha256_file(OUTPUT_PNG),
                                    "width": WIDTH, "height": HEIGHT, "mode": image.mode,
                                    "size_bytes": OUTPUT_PNG.stat().st_size, "image_count": 1}
        report["gpu"]["nvidia_smi_after"] = nvidia_info()
        report["gpu"]["torch_peak_below_40_gib"] = torch.cuda.max_memory_reserved() < 40 * 2**30
        report["gpu"]["memory_measurement_note"] = "Torch allocator peak; native CUDA allocations are not a continuous whole-device peak measurement"
        if not report["gpu"]["torch_peak_below_40_gib"]:
            raise TestAbort("Measured Torch memory peak exceeded the 40 GiB acceptance budget; image not marked successful")
    finally:
        offload_and_collect(mm)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--describe", action="store_true", help="Print immutable manifest only; safe on a CPU VM")
    mode.add_argument("--preflight-only", action="store_true", help="Check assigned Colab GPU/resources, no installs or model downloads")
    mode.add_argument("--setup-only", action="store_true", help="Install and verify pinned assets in Colab, do not sample")
    parser.add_argument("--skip-setup", action="store_true", help="Reuse exact existing install/models; refuse missing files")
    options = parser.parse_args(argv)
    if options.describe:
        print(json.dumps(request_manifest(), indent=2, ensure_ascii=False))
        return 0
    require_colab()  # before directory creation, dependency install, or network access
    os.environ["GIT_TERMINAL_PROMPT"] = "0"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    WORK.mkdir(parents=True, exist_ok=True)
    report = {**request_manifest(), "status": "running", "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "runtime_script_sha256": sha256_file(Path(__file__).resolve()), "timings_seconds": {}}
    started = time.perf_counter()
    try:
        # A previous output must not be confused with this run on failure.
        if OUTPUT_PNG.exists():
            raise TestAbort("Output PNG already exists; move it aside explicitly before rerunning this single-image test")
        with phase(report, "preflight"):
            framework = preflight(report)
        if options.preflight_only:
            report["status"] = "preflight_ok"
            return 0
        with phase(report, "dependencies"):
            if not options.skip_setup:
                missing = sum(item["size"] for item in MODEL_FILES if not (COMFY / "models" / item["local_path"]).is_file())
                if shutil.disk_usage(CONTENT).free < missing + 6 * 2**30:
                    raise TestAbort("Insufficient Colab disk space for exact files plus conservative setup margin")
            setup_dependencies(framework, skip_setup=options.skip_setup)
            # Resolve/import exact nodes BEFORE starting multi-gigabyte downloads.
            node_bundle = load_nodes()
            from comfy.cli_args import args as comfy_args
            report["effective_reserved_vram_gib"] = comfy_args.reserve_vram
            from importlib.metadata import version
            report["packages"] = {name: version(name) for name in [
                "torch", "torchvision", "gguf", "transformers", "huggingface-hub", "safetensors",
                "comfy-kitchen", "comfy-aimdo", "Pillow", "numpy"]}
            for name, expected in framework.items():
                if report["packages"][name] != expected:
                    raise TestAbort("Dependency installation changed Colab's supplied torch/torchvision")
        with phase(report, "model_download_and_hash"):
            prepare_models(report, skip_setup=options.skip_setup)
        if options.setup_only:
            report["status"] = "setup_verified_no_inference"
            return 0
        execute_inference(report, node_bundle=node_bundle)
        report["status"] = "success"
        report["stage"] = "complete"
        print(f"Generated exactly one image: {OUTPUT_PNG}; visual content review remains required", flush=True)
        return 0
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__,
                           "message": str(error) if isinstance(error, TestAbort) else "Runtime failure at recorded stage; no fallback model or paid API invoked"}
        print(json.dumps({"status": "failed", "stage": report.get("stage"), "error": report["error"]}), file=sys.stderr)
        return 1
    finally:
        report["elapsed_seconds"] = round(time.perf_counter() - started, 4)
        report["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
        atomic_json(RESULT_JSON, report)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TestAbort as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
