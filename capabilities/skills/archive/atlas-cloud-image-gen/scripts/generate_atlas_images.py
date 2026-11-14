#!/usr/bin/env python3
"""Reusable Atlas Cloud image generator with async submit + parallel polling.

Usage:
    from generate_atlas_images import AtlasImageGenerator

    gen = AtlasImageGenerator("your_api_key")
    urls = gen.generate_batch(
        prompts=["A sunset", "A mountain"],
        model="baidu/ERNIE-Image-Turbo/text-to-image",
        size="1440x2560",
        quality="low"  # for GPT Image 2 only
    )
    print(urls)  # list of URLs
"""

import requests
import time
import json
from concurrent.futures import ThreadPoolExecutor


class AtlasImageGenerator:
    BASE = "https://api.atlascloud.ai"
    GENERATE_URL = f"{BASE}/api/v1/model/generateImage"
    POLL_FMT = f"{BASE}/api/v1/model/prediction/{{}}"

    def __init__(self, api_key: str):
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def submit(self, prompt: str, model: str, size: str = "1024x1024",
               n: int = 1, **kwargs) -> str:
        """Submit image generation job. Returns prediction_id."""
        payload = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": n,
            "enable_sync_mode": False,
            "enable_base64_output": False,
            **kwargs
        }
        resp = requests.post(self.GENERATE_URL, headers=self.headers,
                             json=payload, timeout=30)
        data = resp.json()
        if data.get("code") != 200:
            raise Exception(f"Submit failed: {data}")
        return data["data"]["id"]

    def poll_result(self, prediction_id: str) -> str | None:
        """Poll a single prediction. Returns URL or None (still processing)."""
        resp = requests.get(self.POLL_FMT.format(prediction_id),
                            headers={"Authorization": self.headers["Authorization"]},
                            timeout=10)
        r = resp.json()
        status = r["data"]["status"]
        if status == "completed":
            return r["data"]["outputs"][0]
        elif status == "failed":
            raise Exception(f"Failed: {r['data'].get('error', 'unknown')}")
        return None

    def generate_single(self, prompt: str, model: str,
                        size: str = "1024x1024", max_wait: int = 300,
                        **kwargs) -> str:
        """Generate one image. Returns URL."""
        pred_id = self.submit(prompt, model, size, 1, **kwargs)
        for _ in range(max_wait // 3):
            url = self.poll_result(pred_id)
            if url:
                return url
            time.sleep(3)
        raise Exception(f"Timed out: {pred_id}")

    def generate_batch(self, prompts: list, model: str,
                       size: str = "1024x1024", max_wait: int = 300,
                       **kwargs) -> list:
        """Generate multiple images in parallel. Returns list of [url, None, url, ...]."""
        # Submit all
        pred_ids = []
        for i, prompt in enumerate(prompts):
            try:
                pid = self.submit(prompt, model, size, 1, **kwargs)
                pred_ids.append(pid)
            except Exception as e:
                print(f"[!] Submit #{i+1} failed: {e}")
                pred_ids.append(None)

        results = [None] * len(prompts)

        # Poll all in lockstep
        for _ in range(max_wait // 3):
            all_done = True
            for i, pid in enumerate(pred_ids):
                if results[i] is not None or pid is None:
                    continue
                all_done = False
                try:
                    url = self.poll_result(pid)
                    if url:
                        results[i] = url
                        print(f"[✓] #{i+1} done: {url}")
                except Exception as e:
                    results[i] = "FAILED"
                    print(f"[✗] #{i+1} failed: {e}")
            if all_done:
                break
            time.sleep(3)

        return results
