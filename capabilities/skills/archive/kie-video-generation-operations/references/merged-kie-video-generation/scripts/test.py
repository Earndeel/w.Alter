#!/usr/bin/env python3
"""
Quick Kie.ai API validation script.
Usage: python3 test-kie.py [--poll]
"""

import json, subprocess, sys, time, urllib.request, urllib.error

def vault_get(key_path):
    try:
        return subprocess.check_output(["vault", "get", key_path], text=True).strip()
    except Exception as e:
        print(f"❌ vault read failed: {e}")
        sys.exit(1)

def submit_job(api_key, model="bytedance/seedance-2-fast", duration=5):
    payload = {
        "model": model,
        "input": {
            "prompt": "A serene beach at sunset with gentle waves, cinematic lighting",
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "duration": duration,
            "generate_audio": False,
        },
    }
    req = urllib.request.Request(
        "https://api.kie.ai/api/v1/jobs/createTask",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def poll_task(api_key, task_id, max_attempts=30):
    url = f"https://api.kie.ai/api/v1/jobs/getTaskDetail?taskId={task_id}"
    for i in range(max_attempts):
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            status = data.get("data", {}).get("status", data.get("status", "unknown"))
            print(f"  [{i+1}/{max_attempts}] status = {status}")
            if status in ("completed", "success", "failed", "error"):
                return data
        time.sleep(5)
    return None

def main():
    key = vault_get("kie/api_key")
    print(f"🔐 Key loaded ({len(key)} chars)")
    result = submit_job(key)
    print(f"✅ Response: {json.dumps(result, indent=2)}")
    if result.get("code") != 200:
        print("⚠️  API returned error — key is valid but check credits")
        return
    task_id = result.get("data", {}).get("taskId") or result.get("taskId")
    print(f"📋 Task ID: {task_id}")
    if "--poll" in sys.argv:
        final = poll_task(key, task_id)
        if final:
            print(f"🎯 Final:\n{json.dumps(final, indent=2)}")

if __name__ == "__main__":
    main()
