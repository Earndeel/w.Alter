---
name: ideation-visual
description: "Generate project ideas via creative constraints. ALWAYS produce Excalidraw mindmap as visual output."
version: 1.0.0
author: w-alter
tags: [ideation, brainstorming, visual, excalidraw, mindmap]
metadata:
  hermes:
    tags: [ideation, brainstorming, visual, excalidraw, mindmap]
    related_skills: [excalidraw-chromium-bridge, excalidraw]
---

# Ideation with Visual Output

Generate project ideas, brainstorm solutions, and present complex information with **mandatory Excalidraw mindmap deliverables**.

## When to use

- Brainstorming new features or projects
- Presenting architectural decisions
- Comparing options (models, tools, approaches)
- Breaking down complex systems
- Strategic planning and roadmaps

## Workflow

### 1. Ideation phase
- Use creative constraints (SCAMPER, reverse thinking, random input)
- Generate 3-7 top-level branches
- Each branch: 3-8 leaf ideas
- Score by feasibility, impact, effort

### 2. Visual output (MANDATORY)
After ideation, produce an Excalidraw mindmap (.excalidraw):

**Layout:**
- Left-to-right tree: root → branches → leaves
- Use FlowChartCreator.createNodes() via fiber tree (NEVER manual arrows)
- Reposition after creation (20px+ gap between leaves, 32px between clusters)

**Styling:**
- Color-code branches by category:
  - Blue (#e7f5ff, stroke #1971c2) = technical/infrastructure
  - Green (#d3f9d8, stroke #2f9e44) = features/growth
  - Orange (#ffe8cc, stroke #e67700) = risks/challenges
  - Purple (#e5dbff, stroke #7048e8) = creative/design
  - Red (#ffc9c9, stroke #c92a2a) = blockers/critical
  - Yellow (#fff3bf, stroke #e67700) = opportunities
- Stroke width: 3=critical, 2=important, 1=secondary
- Pill sizing: proportional to text (fontSize * 0.58 * len + 24px)
- Group labels: standalone rectangles for phases/categories

**Text:**
- Root: emoji + title (fontSize 18-20)
- Branches: emoji + name + score/priority (fontSize 14)
- Leaves: emoji + detail + description (fontSize 11-12)
- Font: fontFamily 2 (sans-serif), roughness 0

### 3. Delivery
- Build self-contained HTML viewer (Excalidraw CDN + embedded JSON) via Python script
- SCP `.excalidraw` + HTML viewer to Mac Desktop
- `ssh ... "open ~/Desktop/file.html"` — opens directly in Brave
- Preview via vision_analyze
- Summary table in chat (branch → key ideas → scores)

## Pitfalls

1. **NEVER draw arrows manually** — use FlowChartCreator only
2. **Always reposition** after creation — leaves overlap otherwise
3. **Minimum 20px gap** between leaves
4. **Text must fit** in pills — compute width dynamically
5. **Color-code consistently** — same stroke for branch + its arrows

## Reference
- Skill: excalidraw-chromium-bridge
- File: references/flowchart-creator-api.md
