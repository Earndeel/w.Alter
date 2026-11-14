#!/usr/bin/env python3
"""Quick OpenRouter model lookup. Usage: python3 model_lookup.py <query>

The model list (https://openrouter.ai/api/v1/models) is public: no key is needed. A key is used only when the
caller injected OPENROUTER_API_KEY explicitly; this script never reads a key file (Hermes' .env retired 2026-11-11).
"""
import os
import sys

import requests


def lookup_model(query):
    key = os.environ.get("OPENROUTER_API_KEY", "")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    r = requests.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=30)
    r.raise_for_status()
    models = r.json().get("data", [])
    q = query.lower()
    return [{"id": m["id"], "name": m.get("name", ""), "prompt": m.get("pricing", {}).get("prompt", "?"),
             "completion": m.get("pricing", {}).get("completion", "?")}
            for m in models if q in m.get("id", "").lower() or q in m.get("name", "").lower()]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 model_lookup.py <query>"); sys.exit(1)
    matches = lookup_model(" ".join(sys.argv[1:]))
    if not matches:
        print(f"No models found for: {' '.join(sys.argv[1:])}"); sys.exit(1)
    for m in matches:
        print(f"  {m['id']}  ({m['name']})  prompt={m['prompt']}  completion={m['completion']}")
    if len(matches) == 1:
        print(f"\nUse: {matches[0]['id']}")
