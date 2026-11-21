#!/usr/bin/env python3
"""Skill Intelligence Loop — Phase 1: Quality Audit

Scans all installed skills, grades them on 5 criteria (structure, linked files,
freshness, usage, specificity), and outputs a JSON report + markdown summary.

Usage:
    python3 skill_quality_audit.py [--json] [--output DIR]

Output:
    - audit-{date}.json  (machine-readable)
    - audit-{date}.md    (human-readable summary)
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
SKILLS_DIR = HERMES_HOME / "skills"
AUDIT_DIR = HERMES_HOME / "skill-audit"
USAGE_DB = HERMES_HOME / "skill-usage.json"


def ensure_audit_dir():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Skill discovery
# ---------------------------------------------------------------------------

def discover_skills() -> list[dict]:
    """Find all installed SKILL.md files and parse frontmatter."""
    skills = []
    for skill_md in sorted(SKILLS_DIR.rglob("SKILL.md")):
        try:
            content = skill_md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # Skip test fixtures
        if "tests/" in str(skill_md) or "__pycache__" in str(skill_md):
            continue

        fm = _parse_frontmatter(content)
        skill_dir = skill_md.parent
        name = fm.get("name") or skill_dir.name
        category = _infer_category(skill_dir, skill_md)

        skills.append({
            "name": name,
            "path": str(skill_dir),
            "category": category,
            "description": fm.get("description", "").strip()[:200],
            "version": fm.get("version", ""),
            "content": content,
            "dir": skill_dir,
        })
    return skills


def _parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from SKILL.md content."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return {}
    try:
        import yaml
        return yaml.safe_load(match.group(1)) or {}
    except Exception:
        # Fallback: parse key-value pairs manually
        fm = {}
        for line in match.group(1).split("\n"):
            if ":" in line:
                key, _, val = line.partition(":")
                fm[key.strip()] = val.strip().strip("'\"")
        return fm


def _infer_category(skill_dir: Path, skill_md: Path) -> str:
    """Infer category from directory structure."""
    rel = skill_dir.relative_to(SKILLS_DIR)
    parts = rel.parts
    if len(parts) > 1:
        return parts[0]
    # Check if skill_md has category in path
    rel2 = skill_md.relative_to(SKILLS_DIR)
    if len(rel2.parts) > 1:
        return rel2.parts[0]
    return "uncategorized"


# ---------------------------------------------------------------------------
# Quality grading (0-100)
# ---------------------------------------------------------------------------

def grade_skill(skill: dict, usage_data: dict) -> dict:
    """Grade a skill on 5 criteria, each 0-20 points."""
    content = skill["content"]
    name = skill["name"]
    skill_dir = skill["dir"]

    scores = {}
    issues = []

    # 1. Structure (0-20)
    structure_score = 0
    has_when = bool(re.search(r"##\s*When\s*to\s*Use", content, re.IGNORECASE))
    has_steps = bool(re.search(r"##\s*(Steps|Quick\s*Start|Setup|Configuration)", content, re.IGNORECASE))
    has_pitfalls = bool(re.search(r"##\s*Pitfalls", content, re.IGNORECASE))
    has_verification = bool(re.search(r"##\s*Verification", content, re.IGNORECASE))

    if has_when:
        structure_score += 7
    else:
        issues.append("Missing '## When to Use' section")
    if has_steps:
        structure_score += 5
    else:
        issues.append("Missing steps/setup section")
    if has_pitfalls:
        structure_score += 5
    else:
        issues.append("Missing pitfalls section")
    if has_verification:
        structure_score += 3
    # Bonus for good structure
    if len(content) > 500:
        structure_score += 2  # not just a stub

    scores["structure"] = min(20, structure_score)

    # 2. Linked files (0-20)
    linked_score = 0
    ref_dir = skill_dir / "references"
    tmpl_dir = skill_dir / "templates"
    script_dir = skill_dir / "scripts"
    assets_dir = skill_dir / "assets"

    ref_count = len(list(ref_dir.glob("*"))) if ref_dir.exists() else 0
    tmpl_count = len(list(tmpl_dir.glob("*"))) if tmpl_dir.exists() else 0
    script_count = len(list(script_dir.glob("*"))) if script_dir.exists() else 0
    assets_count = len(list(assets_dir.glob("*"))) if assets_dir.exists() else 0
    total_linked = ref_count + tmpl_count + script_count + assets_count

    if total_linked >= 5:
        linked_score = 20
    elif total_linked >= 3:
        linked_score = 15
    elif total_linked >= 1:
        linked_score = 10
    elif total_linked == 0:
        linked_score = 0
        issues.append("No linked files (references/templates/scripts)")

    scores["linked_files"] = linked_score

    # 3. Freshness (0-20)
    freshness_score = 15  # default: assume reasonably fresh
    try:
        mtime = skill_dir.stat().st_mtime
        age_days = (datetime.now(timezone.utc) - datetime.fromtimestamp(mtime, tz=timezone.utc)).days
        if age_days <= 30:
            freshness_score = 20
        elif age_days <= 60:
            freshness_score = 15
        elif age_days <= 90:
            freshness_score = 10
            issues.append(f"Skill is {age_days} days old — may be stale")
        else:
            freshness_score = 5
            issues.append(f"Skill is {age_days} days old — likely stale")
    except OSError:
        freshness_score = 10

    scores["freshness"] = freshness_score

    # 4. Usage (0-20)
    usage_score = 0
    rec = usage_data.get(name, {})
    use_count = rec.get("use_count", 0)
    view_count = rec.get("view_count", 0)
    last_used = rec.get("last_used_at")

    if use_count >= 10:
        usage_score = 20
    elif use_count >= 5:
        usage_score = 15
    elif use_count >= 1:
        usage_score = 10
    elif view_count >= 1:
        usage_score = 5
    else:
        usage_score = 0
        # Don't flag built-in skills as unused
        if not name.startswith("hermes-"):
            issues.append(f"Never used (views: {view_count})")

    scores["usage"] = usage_score

    # 5. Specificity (0-20) — heuristic: content length + unique terms
    specificity_score = 10  # default
    content_lines = len(content.split("\n"))
    if content_lines >= 200:
        specificity_score = 18
    elif content_lines >= 100:
        specificity_score = 14
    elif content_lines >= 50:
        specificity_score = 10
    else:
        specificity_score = 5
        issues.append("Very short content — may lack specificity")

    # Check for duplicate indicators (very generic content)
    generic_markers = ["generic", "placeholder", "TODO", "FIXME", "TBD"]
    generic_count = sum(1 for m in generic_markers if m.lower() in content.lower())
    if generic_count >= 3:
        specificity_score = max(0, specificity_score - 5)
        issues.append("Contains generic/placeholder content")

    scores["specificity"] = specificity_score

    # Final grade
    total = sum(scores.values())
    if total >= 80:
        letter = "A"
    elif total >= 60:
        letter = "B"
    elif total >= 40:
        letter = "C"
    else:
        letter = "D"

    return {
        "name": name,
        "category": skill["category"],
        "description": skill["description"],
        "total": total,
        "letter": letter,
        "scores": scores,
        "issues": issues,
        "content_lines": content_lines,
        "linked_files": total_linked,
    }


# ---------------------------------------------------------------------------
# Usage data loader
# ---------------------------------------------------------------------------

def load_usage_data() -> dict:
    """Load skill usage records from the Hermes skill-usage store."""
    # Try the JSON file first (simpler)
    if USAGE_DB.exists():
        try:
            data = json.loads(USAGE_DB.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: try the Python module (if available in the hermes-agent checkout)
    try:
        sys.path.insert(0, str(HERMES_HOME / "hermes-agent"))
        from tools.skill_usage import _load_db
        return _load_db() if callable(_load_db) else {}
    except Exception:
        pass

    return {}


# ---------------------------------------------------------------------------
# Gap detection (simplified)
# ---------------------------------------------------------------------------

def detect_gaps(skills: list[dict]) -> list[dict]:
    """Identify categories with few skills and common tool patterns without coverage."""
    gaps = []

    # Category coverage analysis
    categories = {}
    for s in skills:
        cat = s["category"]
        categories.setdefault(cat, []).append(s["name"])

    # Thin categories (< 3 skills)
    for cat, names in sorted(categories.items()):
        if len(names) < 3:
            gaps.append({
                "type": "thin_category",
                "category": cat,
                "count": len(names),
                "skills": names,
                "recommendation": f"Search store for more {cat} skills",
            })

    # Check for common patterns without dedicated skills
    all_content = " ".join(s["content"].lower() for s in skills)
    common_patterns = [
        ("stripe", "payment integration"),
        ("docker", "containerization"),
        ("kubernetes", "orchestration"),
        ("terraform", "infrastructure as code"),
        ("graphql", "API query language"),
        ("websocket", "real-time communication"),
        ("redis", "caching/session store"),
        ("elasticsearch", "search engine"),
        ("s3", "object storage"),
        ("cloudflare", "CDN/edge computing"),
    ]

    for keyword, description in common_patterns:
        if keyword in all_content:
            # Check if there's a dedicated skill for this
            has_dedicated = any(
                keyword in s["name"].lower() or keyword in s["description"].lower()
                for s in skills
            )
            if not has_dedicated:
                gaps.append({
                    "type": "missing_dedicated",
                    "keyword": keyword,
                    "description": description,
                    "recommendation": f"Consider creating or installing a dedicated {keyword} skill",
                })

    return gaps


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(results: list[dict], gaps: list[dict], output_dir: Path):
    """Write JSON and Markdown reports."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    json_path = output_dir / f"audit-{now}.json"
    md_path = output_dir / f"audit-{now}.md"

    # JSON
    report = {
        "date": now,
        "total_skills": len(results),
        "grades": {
            "A": len([r for r in results if r["letter"] == "A"]),
            "B": len([r for r in results if r["letter"] == "B"]),
            "C": len([r for r in results if r["letter"] == "C"]),
            "D": len([r for r in results if r["letter"] == "D"]),
        },
        "average_score": round(sum(r["total"] for r in results) / max(len(results), 1), 1),
        "skills": [{k: v for k, v in r.items() if k != "content"} for r in results],
        "gaps": gaps,
    }
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Markdown
    lines = [
        f"# Skill Intelligence Report — {now}",
        "",
        f"**Total skills:** {len(results)}  ",
        f"**Average score:** {report['average_score']}/100  ",
        f"**Grades:** A={report['grades']['A']} · B={report['grades']['B']} · C={report['grades']['C']} · D={report['grades']['D']}",
        "",
        "## Quality Grades",
        "",
        "| Skill | Grade | Structure | Links | Fresh | Usage | Specific | Issues |",
        "|-------|-------|-----------|-------|-------|-------|----------|--------|",
    ]

    for r in sorted(results, key=lambda x: x["total"]):
        s = r["scores"]
        issues_str = "; ".join(r["issues"][:2]) if r["issues"] else "—"
        lines.append(
            f"| {r['name']} | {r['letter']} ({r['total']}) "
            f"| {s['structure']} | {s['linked_files']} | {s['freshness']} "
            f"| {s['usage']} | {s['specificity']} | {issues_str} |"
        )

    if gaps:
        lines.extend(["", "## Gaps Detected", ""])
        for g in gaps:
            if g["type"] == "thin_category":
                lines.append(f"- **{g['category']}**: only {g['count']} skills ({', '.join(g['skills'])}) → {g['recommendation']}")
            elif g["type"] == "missing_dedicated":
                lines.append(f"- **{g['keyword']}** ({g['description']}): referenced but no dedicated skill → {g['recommendation']}")

    # Decomposition candidates
    big_skills = [r for r in results if r["content_lines"] > 300]
    if big_skills:
        lines.extend(["", "## Decomposition Candidates (>300 lines)", ""])
        for r in big_skills:
            lines.append(f"- **{r['name']}** ({r['content_lines']} lines, grade {r['letter']})")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Skill quality audit")
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    parser.add_argument("--output", default=str(AUDIT_DIR), help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output)
    ensure_audit_dir()

    print("🔍 Discovering skills...", file=sys.stderr)
    skills = discover_skills()
    print(f"   Found {len(skills)} skills", file=sys.stderr)

    print("📊 Loading usage data...", file=sys.stderr)
    usage_data = load_usage_data()
    print(f"   Loaded {len(usage_data)} usage records", file=sys.stderr)

    print("📝 Grading skills...", file=sys.stderr)
    results = []
    for skill in skills:
        grade = grade_skill(skill, usage_data)
        results.append(grade)
        if grade["letter"] in ("C", "D"):
            print(f"   ⚠️  {skill['name']}: {grade['letter']} ({grade['total']}/100)", file=sys.stderr)

    print("🔎 Detecting gaps...", file=sys.stderr)
    gaps = detect_gaps(skills)
    if gaps:
        print(f"   Found {len(gaps)} gaps", file=sys.stderr)

    print("📄 Generating reports...", file=sys.stderr)
    json_path, md_path = generate_report(results, gaps, output_dir)
    print(f"   {json_path}", file=sys.stderr)
    print(f"   {md_path}", file=sys.stderr)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        # Print summary
        avg = round(sum(r["total"] for r in results) / max(len(results), 1), 1)
        print(f"\n✅ Audit complete: {len(results)} skills, avg {avg}/100")
        print(f"   A={len([r for r in results if r['letter'] == 'A'])} "
              f"B={len([r for r in results if r['letter'] == 'B'])} "
              f"C={len([r for r in results if r['letter'] == 'C'])} "
              f"D={len([r for r in results if r['letter'] == 'D'])}")


if __name__ == "__main__":
    main()
