"""
pxpipe page filler — assembleur de payload optimisé pour remplissage à ~95% (47K/48K chars)

Usage:
  from fill_page import assemble_payload
  system, user_msg = assemble_payload(
      base_template_path="templates/planner-payload.md",
      task="...",
      history=[{"role":"user","content":"..."},{"role":"assistant","content":"..."}],
      relevant_skills=["model-router-intelligence-loop","walter-operating-mode"],
      extra_context="..."
  )
"""

import os
from pathlib import Path

PAGE_SIZE = 48000    # pxpipe page capacity (chars)
TARGET = 47000       # target fill level (chars) — ~98%
# Break-even: at ~2,684 tokens per image, pxpipe costs the same as ~9,100 chars of text
# Image cost is FIXED regardless of fill percentage — so if using pxpipe, pack the page
MIN_PAGE = 9100      # below this, skip pxpipe (text is cheaper)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent  # ~/.hermes/skills

# ---------------------------------------------------------------------------
# Detailed tool schemas (for padding — added when space allows)
# ---------------------------------------------------------------------------
TOOL_SCHEMAS_DETAILED = """
TOOL SCHEMAS:
web_search(query:str, limit:int=5) → {data:{web:[{url,title,description}]}}
web_extract(urls:list[str], char_limit:int=15000) → {results:[{url,title,content,error}]}
terminal(command:str, background:bool=false, timeout:int=300, pty:bool=false) → {output,exit_code}
read_file(path:str, offset:int=1, limit:int=500) → {content,total_lines}
write_file(path:str, content:str) → overwrites file, auto-lint
patch(path:str, old_string:str, new_string:str) → fuzzy matching, unified diff
search_files(pattern:str, path:str, target:content|files, file_glob:str?) → {matches}
browser_navigate(url:str) → browser session + snapshot
browser_snapshot(full:bool=false) → accessibility tree with ref IDs
browser_click(ref:str) → click element by ref
browser_type(ref:str, text:str) → type into field
browser_vision(question:str, annotate:bool=false) → screenshot
delegate_task(goal:str, context:str?, tasks:list?) → subagents (max 3)
execute_code(code:str) → Python with hermes_tools, 50 calls max, 5min timeout
memory(action:add|replace|remove, target:user|memory) → persistent, inter-session
skill_view(name:str, file_path:str?) → load skill + linked files
skill_manage(action:create|patch|delete, name:str, content?) → CRUD skills
clarify(question:str, choices:list[str]?) → ask user, multi-choice
cronjob(action:create|list|remove, schedule:str, prompt:str?) → scheduled jobs
session_search(query:str, session_id:str?, around_message_id:int?) → FTS5 transcripts
hindsight_recall(query:str) → semantic search long-term memory
hindsight_reflect(query:str) → reasoned synthesis from memory
hindsight_retain(content:str, context:str?, tags:list?) → store memory
vision_analyze(image_url:str, question:str) → load image for analysis
image_generate(prompt:str, aspect_ratio:landscape|square|portrait) → image gen
text_to_speech(text:str) → audio conversion
"""

# ---------------------------------------------------------------------------
# Skill detail expander — loads full skill summaries when space allows
# ---------------------------------------------------------------------------
SKILL_DETAILS = {}
CORE_SKILLS = [
    "pxpipe-vision-compression",
    "pxpipe-planning-proxy",
    "model-router-intelligence-loop",
    "aa-intel-vs-cost-scraper",
    "model-benchmark-comparison",
    "computer-use",
    "cloudflare-mcp-mastery",
    "github-workflow-mastery",
    "kanban-suite",
    "anti-bot-navigation",
    "web-extraction-fallbacks",
    "telegram-bot-pool",
    "scena-video-factory",
]


def _load_skill_detail(name: str) -> str:
    """Try to load a skill's description from its SKILL.md frontmatter."""
    skill_path = SKILL_DIR / "devops" / name / "SKILL.md"
    if not skill_path.exists():
        # search other directories
        for cat in SKILL_DIR.iterdir():
            p = cat / name / "SKILL.md"
            if p.exists():
                skill_path = p
                break
    if not skill_path.exists():
        return f"- {name}: skill disponible"
    
    try:
        content = skill_path.read_text()
        # Extract description from frontmatter
        desc = f"- {name}: "
        in_frontmatter = False
        for line in content.split("\n"):
            if line.strip() == "---":
                if not in_frontmatter:
                    in_frontmatter = True
                    continue
                else:
                    break
            if in_frontmatter and line.startswith("description:"):
                desc += line.split("description:", 1)[1].strip()
                break
        else:
            desc += "skill disponible"
        return desc
    except Exception:
        return f"- {name}: skill disponible"


def load_skill_details(names: list[str]) -> str:
    """Load descriptions for a list of skills (with cache)."""
    lines = []
    for name in names:
        if name not in SKILL_DETAILS:
            SKILL_DETAILS[name] = _load_skill_detail(name)
        lines.append(SKILL_DETAILS[name])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------

def assemble_payload(
    base_template_path: str,
    task: str,
    history: list[dict] | None = None,
    relevant_skills: list[str] | None = None,
    extra_context: str | None = None,
) -> dict:
    """
    Assemble a pxpipe-optimized payload.
    
    Returns:
        {system, user_msg, total_chars, pct_full, should_use_pxpipe, layers}
    """
    skill_dir = Path(__file__).resolve().parent.parent
    
    # 1. Load base template
    template_path = skill_dir / base_template_path
    if template_path.exists():
        base = template_path.read_text()
        # Strip the ## TÂCHE section — we append dynamic task later
        if "## TÂCHE" in base:
            base = base[:base.index("## TÂCHE")]
    else:
        # fallback: use root skills dir
        base_path = Path("/root/.hermes/skills/devops/pxpipe-planning-proxy") / base_template_path
        if base_path.exists():
            base = base_path.read_text()
            if "## TÂCHE" in base:
                base = base[:base.index("## TÂCHE")]
        else:
            base = ""
    
    used = len(base)
    layers = {"template": len(base)}
    
    # 2. Build history
    history_text = ""
    if history:
        history_text = "\n## HISTORIQUE DE CONVERSATION\n"
        for msg in history[-20:]:  # last 20 messages max
            role = msg.get("role", "user")
            content = str(msg.get("content", ""))[:500]  # truncate per message
            prefix = "Monsieur" if role == "user" else "W.Alter"
            history_text += f"\n### {prefix}\n{content}\n"
        used += len(history_text)
        layers["history"] = len(history_text)
    
    # 3. Relevant skills detail
    skills_text = ""
    if relevant_skills:
        skills_text = "\n## SKILLS PERTINENTS (détail)\n"
        skills_text += load_skill_details(relevant_skills)
        used += len(skills_text)
        layers["skills_detail"] = len(skills_text)
    
    # 4. Extra context
    ctx_text = ""
    if extra_context:
        ctx_text = f"\n## CONTEXTE ADDITIONNEL\n{extra_context}\n"
        used += len(ctx_text)
        layers["extra_context"] = len(ctx_text)
    
    # 5. Task (always at the end)
    task_text = f"\n## TÂCHE\n{task}\n"
    used += len(task_text)
    layers["task"] = len(task_text)
    
    # 6. Tool schemas detail (padding)
    padding_needed = TARGET - used
    tool_detail_text = ""
    if padding_needed > len(TOOL_SCHEMAS_DETAILED) + 100:
        tool_detail_text = f"\n{TOOL_SCHEMAS_DETAILED}\n"
        used += len(tool_detail_text)
        layers["tool_schemas"] = len(tool_detail_text)
    
    # 7. Load ALL core skill details as final padding
    padding_needed = TARGET - used
    if padding_needed > 500:
        all_skills_text = "\n## SKILLS CHARGE (complément)\n"
        remaining = padding_needed - 100
        for s in CORE_SKILLS:
            line = _load_skill_detail(s)
            if len(all_skills_text) + len(line) > remaining:
                break
            all_skills_text += line + "\n"
        used += len(all_skills_text)
        layers["all_skills_padding"] = len(all_skills_text)
    else:
        all_skills_text = ""
    
    # Final assembly
    system = base + history_text + skills_text + ctx_text + tool_detail_text + all_skills_text
    user_msg = task_text
    
    total = len(system) + len(user_msg)
    pct = total / PAGE_SIZE * 100
    
    return {
        "system": system,
        "user_msg": user_msg,
        "total_chars": total,
        "pct_full": pct,
        "should_use_pxpipe": total > MIN_PAGE,
        "layers": layers,
    }
