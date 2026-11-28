#!/usr/bin/env python3
"""
Execute a Fal.ai Sana workflow via local ComfyUI REST API.
No GPU required — all generation happens on Fal.ai servers.

Usage:
    python3 scripts/fal_sana_executor.py "a cyberpunk city at night, neon lights"
    python3 scripts/fal_sana_executor.py                    # uses default prompt

Requires:
    - ComfyUI running on http://127.0.0.1:8188
    - ComfyUI-fal-API custom nodes installed
    - FAL_KEY env var or config.ini set
"""
import json
import urllib.request
import sys
import os
import time


def run_workflow(
    prompt="a majestic lion in a savanna at golden hour, highly detailed, 8k quality",
    negative_prompt="blurry, low quality, distorted",
    seed=42,
    steps=20,
    host="http://127.0.0.1:8188",
):
    workflow = {
        "1": {
            "class_type": "Sana_fal",
            "inputs": {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "image_size": "square_hd",
                "width": 1024,
                "height": 1024,
                "num_inference_steps": steps,
                "guidance_scale": 5.0,
                "num_images": 1,
                "seed": seed,
                "enable_safety_checker": True,
                "output_format": "png",
            },
        },
        "2": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["1", 0],
                "filename_prefix": "fal_sana_output",
            },
        },
    }

    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"{host}/api/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
        prompt_id = result["prompt_id"]
        print(f"Job submitted: {prompt_id}")

    # Poll for result
    for _ in range(60):
        time.sleep(2)
        req = urllib.request.Request(f"{host}/api/history/{prompt_id}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            history = json.loads(resp.read())
            entry = history.get(prompt_id, {})
            if entry.get("status", {}).get("completed"):
                outputs = entry.get("outputs", {})
                for node_id, node_out in outputs.items():
                    if "images" in node_out:
                        for img in node_out["images"]:
                            filename = img["filename"]
                            local_url = f"{host}/api/view?filename={filename}&subfolder=&type=output"
                            print(f"Output: {filename}")
                            print(f"Local:  {local_url}")
                return entry

    raise TimeoutError("Job did not complete in 120s")


if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else "a majestic lion in a savanna at golden hour, highly detailed, 8k quality"
    result = run_workflow(prompt=prompt)
    print("Done!")
