#!/usr/bin/env python3
"""Atlas Cloud ERNIE-Image-Turbo batch generator.
Usage: python3 atlas_ernie_batch.py prompts.json [--size 1440x2560] [--parallel]
prompts.json: ["prompt1", "prompt2", ...]
"""
import requests
import time
import json
import sys
import argparse

BASE = "https://api.atlascloud.ai"
HEADERS = {"Content-Type": "application/json", "Authorization": "Bearer {KEY}"}

def set_key(key):
    HEADERS["Authorization"] = f"Bearer {key}"

def submit(prompt, size="1440x2560"):
    data = {
        "model": "baidu/ERNIE-Image-Turbo/text-to-image",
        "prompt": prompt,
        "size": size,
        "n": 1,
        "enable_sync_mode": False,
        "enable_base64_output": False,
    }
    resp = requests.post(f"{BASE}/api/v1/model/generateImage",
        headers=HEADERS, json=data, timeout=30)
    result = resp.json()
    if result.get("code") != 200:
        raise Exception(f"Submit failed: {result}")
    return result["data"]["id"]

def poll(prediction_id, timeout=120, interval=3):
    url = f"{BASE}/api/v1/model/prediction/{prediction_id}"
    for _ in range(timeout // interval):
        resp = requests.get(url, headers={"Authorization": HEADERS["Authorization"]}, timeout=10)
        d = resp.json()["data"]
        if d["status"] == "completed":
            return d["outputs"][0]
        if d["status"] == "failed":
            return None, d.get("error", "unknown")
        time.sleep(interval)
    return None, "timeout"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prompts_file", help="JSON file with list of prompts")
    parser.add_argument("--size", default="1440x2560")
    parser.add_argument("--key", help="Atlas API key (or set ATLAS_KEY env var)")
    args = parser.parse_args()

    key = args.key or "{{bw:W.Alter · atlas:field:api_key}}"
    set_key(key)

    with open(args.prompts_file) as f:
        prompts = json.load(f)

    start = time.time()
    print(f"Submitting {len(prompts)} images at {args.size}...")

    # Submit all
    ids = []
    for i, p in enumerate(prompts, 1):
        pid = submit(p, args.size)
        ids.append(pid)
        print(f"  [{i}/{len(prompts)}] Submitted: {pid[:12]}...")
        time.sleep(0.3)

    # Poll all
    results = []
    completed = 0
    while completed < len(ids):
        for i, pid in enumerate(ids):
            if results[i] and results[i] is not None:
                continue
            out = poll(pid)
            if out[0] is not None:
                results[i] = out[0]
                completed += 1
                print(f"  ✅ #{i+1}: {out[0]}")
            elif out[1]:
                results[i] = None
                completed += 1
                print(f"  ❌ #{i+1}: {out[1]}")
        time.sleep(3)

    elapsed = time.time() - start
    ok = [r for r in results if r]
    print(f"\n📊 {len(ok)}/{len(prompts)} succeeded in {elapsed:.1f}s")
    print(f"   Avg: {elapsed/len(prompts):.1f}s per image")

if __name__ == "__main__":
    main()
