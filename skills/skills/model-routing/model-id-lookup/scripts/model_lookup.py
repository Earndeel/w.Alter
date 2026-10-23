#!/usr/bin/env python3
"""Quick OpenRouter model lookup. Usage: python3 model_lookup.py <query>"""
import requests, os, sys

def lookup_model(query):
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        env_path = os.path.expanduser("~/.hermes/.env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("OPENROUTER_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not found"); sys.exit(1)
    r = requests.get("https://openrouter.ai/api/v1/models", headers={"Authorization": f"Bearer {api_key}"})
    models = r.json().get("data", [])
    q = query.lower()
    return [{"id": m["id"], "name": m.get("name",""), "prompt": m.get("pricing",{}).get("prompt","?"), "completion": m.get("pricing",{}).get("completion","?")} for m in models if q in m.get("id","").lower() or q in m.get("name","").lower()]

if __name__ == "__main__":
    if len(sys.argv) < 2: print("Usage: python3 model_lookup.py <query>"); sys.exit(1)
    matches = lookup_model(" ".join(sys.argv[1:]))
    if not matches: print(f"No models found for: {' '.join(sys.argv[1:])}"); sys.exit(1)
    for m in matches: print(f"  {m['id']}  ({m['name']})  prompt={m['prompt']}  completion={m['completion']}")
    if len(matches) == 1: print(f"\nUse: {matches[0]['id']}")
