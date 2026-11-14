#!/usr/bin/env python3
"""
Agent Feedback Loop — Update EVOLUTION.md after task completion.

Usage:
  python3 agent_feedback.py feedback \
    --agent forge \
    --task "fix webhook stripe" \
    --type backend \
    --model claude-opus-4-7 \
    --provider kie-claude \
    --result success \
    --time "3min" \
    --lesson "Stripe webhooks need retry on 5xx" \
    --action "Added retry rule to SOUL.md"

  python3 agent_feedback.py list
"""

import argparse
import os
from datetime import datetime
from pathlib import Path


AGENTS_DIR = Path.home() / ".hermes" / "agents"


def update_evolution(agent_name: str, entry: dict):
    """Append an entry to the agent's EVOLUTION.md."""
    evolution_path = AGENTS_DIR / agent_name / "EVOLUTION.md"
    if not evolution_path.exists():
        print(f"Error: EVOLUTION.md not found for agent '{agent_name}'")
        return False

    result_emoji = {
        "success": "✅", "partial": "⚠️", "failed": "❌"
    }.get(entry.get("result", ""), "❓")

    entry_text = f"""
### {datetime.now().strftime('%Y-%m-%d %H:%M')} — Task: {entry.get('task', 'unknown')}
- **Type**: {entry.get('type', 'unknown')}
- **Model used**: {entry.get('model', '?')} / {entry.get('provider', '?')}
- **Result**: {result_emoji} {entry.get('result', 'unknown')}
- **Time**: {entry.get('time', '?')}"""

    if entry.get("sources"):
        entry_text += f"\n- **Sources**: {entry['sources']}"

    entry_text += f"""
- **Lesson**: {entry.get('lesson', 'none recorded')}
- **Action**: {entry.get('action', 'none')}"""

    with open(evolution_path, 'a') as f:
        f.write(entry_text + "\n")

    print(f"✅ Evolution updated for {agent_name}")
    return True


def update_soul(agent_name: str, action: str):
    """If action is a permanent rule, append to SOUL.md."""
    if not action or action == "none":
        return
    soul_path = AGENTS_DIR / agent_name / "SOUL.md"
    if not soul_path.exists():
        return
    permanent_keywords = ["always", "never", "added rule", "workflow change", "new pattern"]
    is_permanent = any(kw in action.lower() for kw in permanent_keywords)
    if is_permanent:
        with open(soul_path, 'a') as f:
            f.write(f"\n\n> **Auto-added {datetime.now().strftime('%Y-%m-%d')}**: {action}")
        print(f"📝 SOUL.md updated with permanent rule: {action}")


def list_agents():
    """List available agents."""
    if not AGENTS_DIR.exists():
        print("No agents directory found")
        return
    for d in sorted(AGENTS_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith('_'):
            soul = d / "SOUL.md"
            evolution = d / "EVOLUTION.md"
            status = "✅" if soul.exists() else "⚠️"
            entries = 0
            if evolution.exists():
                content = evolution.read_text()
                entries = content.count("### 20")
            print(f"  {status} {d.name} ({entries} evolution entries)")


def main():
    parser = argparse.ArgumentParser(description="Agent Feedback Loop")
    sub = parser.add_subparsers(dest="command")

    fb = sub.add_parser("feedback", help="Add feedback to agent's EVOLUTION.md")
    fb.add_argument("--agent", required=True)
    fb.add_argument("--task", required=True)
    fb.add_argument("--type", default="unknown")
    fb.add_argument("--model", default="?")
    fb.add_argument("--provider", default="?")
    fb.add_argument("--result", required=True, choices=["success", "partial", "failed"])
    fb.add_argument("--time", default="?")
    fb.add_argument("--sources", type=int)
    fb.add_argument("--lesson", default="none recorded")
    fb.add_argument("--action", default="none")

    sub.add_parser("list", help="List available agents")

    args = parser.parse_args()

    if args.command == "feedback":
        entry = {
            "task": args.task, "type": args.type, "model": args.model,
            "provider": args.provider, "result": args.result, "time": args.time,
            "sources": args.sources, "lesson": args.lesson, "action": args.action,
        }
        update_evolution(args.agent, entry)
        update_soul(args.agent, args.action)
    elif args.command == "list":
        list_agents()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
