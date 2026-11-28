#!/usr/bin/env python3
"""Skill Gap Detector — analyzes recent sessions to find patterns without skill coverage.

Scans recent session transcripts for:
1. Recurring tool call sequences (same tools used together 3+ times)
2. Long tool chains (5+ tool calls on same topic with no skill loaded)
3. Repeated error→fix patterns (agent fixed same issue multiple times)
4. Frequently referenced external services without dedicated skills

Usage:
    python3 skill_gap_detector.py [--sessions N] [--output DIR] [--json]
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
SESSIONS_DIR = HERMES_HOME / "sessions"
SKILLS_DIR = HERMES_HOME / "skills"
AUDIT_DIR = HERMES_HOME / "skill-audit"


# ---------------------------------------------------------------------------
# Session discovery
# ---------------------------------------------------------------------------

def discover_sessions(limit: int = 30) -> list[dict]:
    """Find recent session JSON files."""
    sessions = []
    if not SESSIONS_DIR.exists():
        return sessions

    for f in sorted(SESSIONS_DIR.glob("session_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            data = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            continue

        title = data.get("title", "")
        messages = data.get("messages", [])
        if not messages:
            continue

        sessions.append({
            "file": f.name,
            "title": title,
            "messages": messages,
            "mtime": f.stat().st_mtime,
        })

    return sessions


# ---------------------------------------------------------------------------
# Pattern extraction
# ---------------------------------------------------------------------------

def extract_tool_patterns(messages: list[dict]) -> list[dict]:
    """Extract tool call sequences from session messages."""
    patterns = []
    current_tools = []
    current_topic = ""

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        # Track topic from user messages
        if role == "user" and isinstance(content, str) and len(content) > 10:
            current_topic = content[:100]

        # Track tool calls
        if role == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                if tool_name:
                    current_tools.append(tool_name)

        # When assistant responds without tools, record the pattern
        if role == "assistant" and not msg.get("tool_calls") and current_tools:
            if len(current_tools) >= 3:
                patterns.append({
                    "tools": current_tools[:],
                    "topic": current_topic,
                    "length": len(current_tools),
                })
            current_tools = []

    return patterns


def extract_skill_context(messages: list[dict]) -> tuple[set[str], bool]:
    """Find which skills were loaded in a session."""
    loaded_skills = set()
    has_skill_loading = False

    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            # Detect skill_view calls
            if "skill_view" in content:
                has_skill_loading = True
                # Try to extract skill names
                matches = re.findall(r'skill_view.*?name["\s:=]+["\']?([a-z0-9-]+)', content)
                loaded_skills.update(matches)

            # Detect skill invocation messages
            match = re.search(r'The user has invoked the "([^"]+)" skill', content)
            if match:
                loaded_skills.add(match.group(1))
                has_skill_loading = True

    return loaded_skills, has_skill_loading


def extract_service_references(messages: list[dict]) -> Counter:
    """Find external services/APIs referenced in sessions."""
    service_patterns = {
        "stripe": r"stripe|checkout|payment",
        "cloudflare": r"cloudflare|wrangler|workers?\.(dev|pages)|D1|R2",
        "fal\.ai": r"fal\.?ai|fal-|fal_",
        "piapi": r"piapi|PiAPI",
        "telegram": r"telegram|bot.*token|sendMessage|webhook.*tg",
        "openrouter": r"openrouter",
        "kie\.ai": r"kie\.ai|kie-",
        "github": r"git(hub)?.com|gh\s+(pr|issue|repo)|pull.request",
        "docker": r"docker|container|dockerfile",
        "supabase": r"supabase",
        "redis": r"redis",
        "postgres": r"postgres|pg_|psql",
        "aws": r"aws|s3|lambda|ec2|dynamodb",
        "gcp": r"gcp|google.cloud|bigquery|firebase",
        "azure": r"azure|microsoft.graph",
        "vercel": r"vercel",
        "netlify": r"netlify",
        "sentry": r"sentry",
        "linear": r"linear\.app|linear_",
        "notion": r"notion\.so|notion_",
        "airtable": r"airtable",
        "huggingface": r"huggingface|hf_|transformers",
        "openai": r"openai|gpt-[34]|chatgpt",
        "anthropic": r"anthropic|claude",
        "elevenlabs": r"elevenlabs",
        "replicate": r"replicate",
    }

    references = Counter()
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            content_lower = content.lower()
            for service, pattern in service_patterns.items():
                if re.search(pattern, content_lower):
                    references[service] += 1

    return references


# ---------------------------------------------------------------------------
# Gap analysis
# ---------------------------------------------------------------------------

def find_skill_gaps(sessions: list[dict]) -> list[dict]:
    """Analyze sessions to find skill gaps."""
    # Aggregate data across sessions
    all_patterns = []
    all_services = Counter()
    tool_pair_counts = Counter()  # pairs of tools used together
    tool_sequence_counts = Counter()  # sequences of 3 tools
    skill_loaded_sessions = 0
    heavy_tool_sessions = []

    for session in sessions:
        messages = session["messages"]
        patterns = extract_tool_patterns(messages)
        loaded_skills, has_skills = extract_skill_context(messages)
        services = extract_service_references(messages)

        all_patterns.extend(patterns)
        all_services += services

        if has_skills:
            skill_loaded_sessions += 1

        # Track tool pairs and sequences
        for p in patterns:
            tools = p["tools"]
            # Pairs
            for i in range(len(tools) - 1):
                pair = tuple(sorted([tools[i], tools[i+1]]))
                tool_pair_counts[pair] += 1
            # Sequences of 3
            for i in range(len(tools) - 2):
                seq = tuple(tools[i:i+3])
                tool_sequence_counts[seq] += 1

            # Heavy tool sessions without skills
            if p["length"] >= 5 and not has_skills:
                heavy_tool_sessions.append({
                    "title": session["title"],
                    "topic": p["topic"],
                    "tools": p["tools"],
                    "length": p["length"],
                })

    gaps = []

    # Noise filter: these tools are too generic to indicate a meaningful pattern
    NOISE_TOOLS = {
        "terminal", "memory", "read_file", "search_files", "patch", "write_file",
        "vision_analyze", "browser_vision", "browser_snapshot", "browser_navigate",
        "skills_list", "skill_view", "skill_manage", "browser_click", "browser_type",
        "session_search", "hindsight_retain", "hindsight_recall", "hindsight_reflect",
        "browser_scroll", "browser_back", "browser_press", "browser_console",
        "todo", "memory", "clarify",
    }

    # 1. Recurring tool sequences (3+ occurrences, must include at least 1 non-noise tool)
    for seq, count in tool_sequence_counts.most_common(40):
        if count >= 3:
            meaningful_tools = [t for t in seq if t not in NOISE_TOOLS]
            if not meaningful_tools:
                continue  # skip pure noise patterns
            gaps.append({
                "type": "recurring_sequence",
                "tools": list(seq),
                "meaningful_tools": meaningful_tools,
                "count": count,
                "recommendation": f"Create a skill for the {' → '.join(meaningful_tools)} workflow ({count}x)",
            })

    # 2. Frequently referenced services without dedicated skills
    installed_skills = set()
    for skill_md in SKILLS_DIR.rglob("SKILL.md"):
        installed_skills.add(skill_md.parent.name.lower())

    for service, count in all_services.most_common(10):
        if count >= 5:
            # Check if there's a dedicated skill
            has_dedicated = any(service.replace(".", "") in s for s in installed_skills)
            if not has_dedicated:
                gaps.append({
                    "type": "missing_service_skill",
                    "service": service,
                    "references": count,
                    "recommendation": f"Create or install a '{service}' skill",
                })

    # 3. Heavy tool sessions without skills
    if heavy_tool_sessions:
        # Group by similar topics
        topic_groups = defaultdict(list)
        for s in heavy_tool_sessions:
            # Simple grouping by first meaningful word
            key = s["topic"][:30] if s["topic"] else "unknown"
            topic_groups[key].append(s)

        for topic, group in topic_groups.items():
            if len(group) >= 2:
                gaps.append({
                    "type": "heavy_no_skill",
                    "count": len(group),
                    "avg_tools": round(sum(g["length"] for g in group) / len(group), 1),
                    "sessions": [g["title"] for g in group[:3]],
                    "recommendation": f"Create a skill for repeated '{topic[:40]}' workflows",
                })

    # 4. Common tool pairs (used together 5+ times, both non-noise, not same tool)
    for pair, count in tool_pair_counts.most_common(20):
        if count >= 5 and pair[0] != pair[1] and pair[0] not in NOISE_TOOLS and pair[1] not in NOISE_TOOLS:
            gaps.append({
                "type": "common_pair",
                "tools": list(pair),
                "count": count,
                "recommendation": f"Tools {pair[0]} + {pair[1]} frequently used together ({count}x)",
            })

    return gaps


# ---------------------------------------------------------------------------
# Skill proposal generation
# ---------------------------------------------------------------------------

def generate_skill_proposal(gap: dict) -> dict | None:
    """Generate a concrete skill proposal for a gap."""
    if gap["type"] == "recurring_sequence":
        tools = gap["tools"]
        name = "-".join(tools[:3])
        return {
            "name": name,
            "trigger": f"Recurring workflow: {' → '.join(tools)} ({gap['count']} sessions)",
            "tools_involved": tools,
            "auto_create": True,
        }

    elif gap["type"] == "missing_service_skill":
        service = gap["service"]
        return {
            "name": f"{service}-integration",
            "trigger": f"Service '{service}' referenced {gap['references']} times without dedicated skill",
            "tools_involved": ["terminal", "web"],
            "auto_create": False,  # needs human review
        }

    elif gap["type"] == "heavy_no_skill":
        return {
            "name": "auto-detected-workflow",
            "trigger": f"Heavy tool usage without skill coverage ({gap['count']} sessions)",
            "tools_involved": [],
            "auto_create": False,
        }

    return None


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(gaps: list[dict], sessions_analyzed: int, output_dir: Path):
    """Write the gap detection report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    json_path = output_dir / "skill-gaps-{now}.json".format(now=now)
    md_path = output_dir / "skill-gaps-{now}.md".format(now=now)

    proposals = [p for p in (generate_skill_proposal(g) for g in gaps) if p]
    auto_creatable = [p for p in proposals if p.get("auto_create")]

    report = {
        "date": now,
        "sessions_analyzed": sessions_analyzed,
        "gaps_found": len(gaps),
        "proposals": len(proposals),
        "auto_creatable": len(auto_creatable),
        "gaps": gaps,
        "proposals_detail": proposals,
    }

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"# Skill Gap Report — {now}",
        "",
        f"**Sessions analyzed:** {sessions_analyzed}  ",
        f"**Gaps found:** {len(gaps)}  ",
        f"**Proposals:** {len(proposals)} ({len(auto_creatable)} auto-creatable)",
        "",
    ]

    if not gaps:
        lines.append("No significant skill gaps detected. Library coverage is good.")
    else:
        lines.append("## Gaps Detected")
        lines.append("")
        for i, gap in enumerate(gaps, 1):
            if gap["type"] == "recurring_sequence":
                lines.append(f"{i}. **Recurring workflow** ({gap['count']}x): `{' → '.join(gap['tools'])}`")
            elif gap["type"] == "missing_service_skill":
                lines.append(f"{i}. **Missing service skill**: `{gap['service']}` ({gap['references']} refs)")
            elif gap["type"] == "heavy_no_skill":
                lines.append(f"{i}. **Heavy tool usage** ({gap['count']} sessions, avg {gap['avg_tools']} tools): {gap.get('sessions', [''])[0][:50]}")
            elif gap["type"] == "common_pair":
                lines.append(f"{i}. **Common pair** ({gap['count']}x): `{gap['tools'][0]}` + `{gap['tools'][1]}`")
            lines.append(f"   → {gap['recommendation']}")
            lines.append("")

    if proposals:
        lines.append("## Skill Proposals")
        lines.append("")
        lines.append("| Name | Trigger | Auto-create |")
        lines.append("|------|---------|-------------|")
        for p in proposals:
            auto = "✅" if p.get("auto_create") else "⏳ Review"
            lines.append(f"| {p['name']} | {p['trigger'][:60]} | {auto} |")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Detect skill gaps from session history")
    parser.add_argument("--sessions", type=int, default=30, help="Number of recent sessions to analyze")
    parser.add_argument("--output", default=str(AUDIT_DIR), help="Output directory")
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"🔍 Analyzing {args.sessions} recent sessions...", file=sys.stderr)
    sessions = discover_sessions(args.sessions)
    print(f"   Found {len(sessions)} sessions with messages", file=sys.stderr)

    print("🔎 Detecting skill gaps...", file=sys.stderr)
    gaps = find_skill_gaps(sessions)
    print(f"   Found {len(gaps)} gaps", file=sys.stderr)

    print("📄 Generating report...", file=sys.stderr)
    json_path, md_path = generate_report(gaps, len(sessions), output_dir)
    print(f"   {json_path}", file=sys.stderr)
    print(f"   {md_path}", file=sys.stderr)

    if args.json:
        report = json.loads(json_path.read_text())
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"\n✅ Gap detection complete: {len(sessions)} sessions, {len(gaps)} gaps found")
        for gap in gaps[:5]:
            print(f"   • {gap['recommendation'][:80]}")


if __name__ == "__main__":
    main()
