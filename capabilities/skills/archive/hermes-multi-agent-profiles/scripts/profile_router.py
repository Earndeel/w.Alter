#!/usr/bin/env python3
"""
Profile Model Router — Intelligent task-to-model routing for Hermes profiles.

Reads smart_model_routing from profile config, matches task text against
keyword routes, and returns the best model+provider for the task.

Usage:
  python3 ~/.hermes/scripts/profile_router.py --profile coder --task "fix the webhook stripe bug"
  python3 ~/.hermes/scripts/profile_router.py --profile coder --task "refais le hero" --cmd
  python3 ~/.hermes/scripts/profile_router.py --profile coder --task "rename var" --json
"""

import yaml
import json
import sys
import os
import re
import shlex
from pathlib import Path


def load_profile_config(profile_name: str) -> dict:
    config_path = Path.home() / ".hermes" / "profiles" / profile_name / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Profile config not found: {config_path}")
    with open(config_path) as f:
        return yaml.safe_load(f)


def normalize(text: str) -> str:
    return text.lower().strip()


def match_route(task: str, routes: list) -> dict | None:
    task_norm = normalize(task)
    task_words = set(re.findall(r'\w+', task_norm))
    best = None
    best_score = 0
    for route in routes:
        match_cfg = route.get("match", {})
        any_keywords = [normalize(k) for k in match_cfg.get("any_keywords", [])]
        exclude_keywords = [normalize(k) for k in match_cfg.get("exclude_keywords", [])]
        excluded = any(ek in task_norm for ek in exclude_keywords)
        if excluded:
            continue
        matched = [k for k in any_keywords if k in task_words or k in task_norm]
        score = len(matched)
        if score > best_score:
            best_score = score
            best = {
                "route": route["name"],
                "model": route["model"],
                "provider": route["provider"],
                "score": score,
                "matched_keywords": matched
            }
    return best


def route_task(profile_name: str, task: str) -> dict:
    config = load_profile_config(profile_name)
    routing = config.get("smart_model_routing", {})
    if not routing.get("enabled", False):
        return {"model": config["model"]["default"], "provider": config["model"]["provider"],
                "route": "default", "matched_keywords": [], "score": 0}
    routes = routing.get("routes", [])
    if not routes:
        return {"model": config["model"]["default"], "provider": config["model"]["provider"],
                "route": "default", "matched_keywords": [], "score": 0}
    match = match_route(task, routes)
    if match and match["score"] > 0:
        return match
    return {"model": config["model"]["default"], "provider": config["model"]["provider"],
            "route": "default", "matched_keywords": [], "score": 0}


def build_hermes_command(profile_name: str, task: str, route: dict) -> str:
    cmd = f'hermes -p {profile_name} chat -Q --source task --skills ""'
    cmd += f' -m {route["model"]} --provider {route["provider"]}'
    cmd += f' -q {shlex.quote(task)}'
    return cmd


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Profile Model Router")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--cmd", action="store_true")
    args = parser.parse_args()
    route = route_task(args.profile, args.task)
    if args.json:
        print(json.dumps(route, indent=2, ensure_ascii=False))
    elif args.cmd:
        print(build_hermes_command(args.profile, args.task, route))
    else:
        print(f"Route:    {route['route']}")
        print(f"Model:    {route['model']}")
        print(f"Provider: {route['provider']}")
        print(f"Score:    {route['score']}")
        if route['matched_keywords']:
            print(f"Keywords: {', '.join(route['matched_keywords'])}")


if __name__ == "__main__":
    main()
