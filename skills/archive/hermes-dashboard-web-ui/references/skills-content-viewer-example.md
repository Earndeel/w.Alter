# Example: Skills Content Viewer + Editor (2026-06-04)

Concrete example of adding a read+edit feature to the Hermes dashboard — API endpoints + frontend component with slide-in panel.

## Backend — GET Endpoint (`hermes_cli/web_server.py`)

Added after the existing `GET /api/skills` endpoint:

```python
@app.get("/api/skills/{name}/content")
async def get_skill_content(name: str):
    from tools.skills_tool import skill_view
    import json as _json
    result = skill_view(name, preprocess=False)
    try:
        data = _json.loads(result)
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid response"}, status_code=500)
    if not data.get("success"):
        return JSONResponse(data, status_code=404)
    return {
        "success": True,
        "name": data.get("name", name),
        "content": data.get("content", ""),
        "description": data.get("description", ""),
        "linked_files": data.get("linked_files"),
    }
```

Key: `skill_view(name, preprocess=False)` returns raw markdown. `preprocess=True` would expand templates.

## Backend — PUT Endpoint (Save)

```python
class SkillContentUpdate(BaseModel):
    content: str

@app.put("/api/skills/{name}/content")
async def update_skill_content(name: str, body: SkillContentUpdate):
    from agent.skill_utils import iter_skill_index_files, get_skills_dir, get_external_skills_dirs

    skills_dir = get_skills_dir()
    all_dirs = [skills_dir] + list(get_external_skills_dirs())

    skill_md = None
    for search_dir in all_dirs:
        if not search_dir.exists(): continue
        direct = search_dir / name
        if direct.is_dir() and (direct / "SKILL.md").exists():
            skill_md = direct / "SKILL.md"; break
        flat = search_dir / f"{name}.md"
        if flat.exists(): skill_md = flat; break

    if not skill_md:
        for search_dir in all_dirs:
            if not search_dir.exists(): continue
            for sf in iter_skill_index_files(search_dir, "SKILL.md"):
                rel = sf.relative_to(search_dir)
                if str(rel.parent) == name or rel.parent.name == name:
                    skill_md = sf; break
            if skill_md: break

    if not skill_md:
        return JSONResponse({"success": False, "error": f"Skill '{name}' not found"}, status_code=404)

    skill_md.write_text(body.content, encoding="utf-8")

    # CRITICAL: invalidate snapshot cache
    snapshot = skills_dir / ".skills_prompt_snapshot.json"
    if snapshot.exists(): snapshot.unlink()

    return {"success": True, "name": name, "path": str(skill_md)}
```

**Pitfall**: MUST delete `.skills_prompt_snapshot.json` after writing. This file caches parsed frontmatter/descriptions — stale snapshots cause the system prompt to show outdated skill metadata until a cold restart.

## Frontend API — `web/src/lib/api.ts`

```typescript
getSkillContent: (name: string) =>
  fetchJSON<{ success: boolean; name: string; content: string; description: string; linked_files: Record<string, string[]> | null }>(
    `/api/skills/${encodeURIComponent(name)}/content`,
  ),
saveSkillContent: (name: string, content: string) =>
  fetchJSON<{ success: boolean; name: string; path: string }>(
    `/api/skills/${encodeURIComponent(name)}/content`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    },
  ),
```

## Frontend UI — `web/src/pages/SkillsPage.tsx`

### State

```tsx
const [selectedSkill, setSelectedSkill] = useState<string | null>(null);
const [skillContent, setSkillContent] = useState<string | null>(null);
const [skillLinkedFiles, setSkillLinkedFiles] = useState<Record<string, string[]> | null>(null);
const [loadingContent, setLoadingContent] = useState(false);
const [editing, setEditing] = useState(false);
const [editContent, setEditContent] = useState("");
const [saving, setSaving] = useState(false);
```

### SkillRow — Make clickable

Added `onViewContent` prop to `SkillRowProps`. The skill name area becomes clickable with a ChevronRight icon that appears on hover:

```tsx
<div className="flex-1 min-w-0 cursor-pointer" onClick={onViewContent}>
  <div className="flex items-center gap-2 mb-0.5">
    <span className="font-mono-ui text-sm">{skill.name}</span>
    <ChevronRight className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
  </div>
</div>
```

### Slide-in Panel

Full-screen overlay with a right-side panel (max-w-2xl). Click backdrop to close. Header has Edit/Cancel/Save buttons. Content switches between `<pre>` (read mode) and `<textarea>` (edit mode).

### Edit Mode Pattern

```tsx
// Header buttons
{!editing && skillContent && (
  <Button ghost size="xs" onClick={startEditing}>Edit</Button>
)}
{editing && (
  <>
    <Button ghost size="xs" onClick={cancelEditing}>Cancel</Button>
    <Button size="xs" onClick={saveEditing} disabled={saving}>
      {saving ? "Saving..." : "Save"}
    </Button>
  </>
)}

// Content area
{editing ? (
  <textarea
    className="w-full h-full min-h-[60vh] font-mono text-xs ..."
    value={editContent}
    onChange={(e) => setEditContent(e.target.value)}
    spellCheck={false}
  />
) : skillContent ? (
  <pre className="whitespace-pre-wrap ...">{skillContent}</pre>
)}
```

## Build & Restart

```bash
cd web && npm run build                     # frontend only
hermes dashboard --stop                      # stop old process
hermes dashboard --host 0.0.0.0 --insecure --no-open --port 9119  # restart
```

Frontend changes need `npm run build`. Backend changes need dashboard restart.

## Testing

```python
import requests, re
r = requests.get("http://127.0.0.1:9119/skills")
token = re.search(r'__HERMES_SESSION_TOKEN__="([^"]+)"', r.text).group(1)
headers = {"Authorization": f"Bearer {token}"}

# Read
requests.get("http://127.0.0.1:9119/api/skills/arxiv/content", headers=headers)

# Write
requests.put("http://127.0.0.1:9119/api/skills/arxiv/content",
    headers=headers, json={"content": "# updated"})
```
