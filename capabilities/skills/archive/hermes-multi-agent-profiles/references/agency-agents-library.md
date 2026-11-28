# Agency-Agents Library Integration

## Source

https://github.com/msitarzewski/agency-agents — 186 specialized AI agent personalities organized in 16 divisions.

## Import

```bash
git clone --depth 1 https://github.com/msitarzewski/agency-agents.git /tmp/agency-agents

# Import all into agent store library
for div in engineering design marketing product specialized testing finance sales support strategy game academic spatial project-management paid-media; do
  mkdir -p ~/.hermes/agents/_library/$div
  cp /tmp/agency-agents/$div/*.md ~/.hermes/agents/_library/$div/ 2>/dev/null
done
```

## What Agency-Agents Provides

Each agent .md file contains:
- **Identity & Memory** — who the agent is, what it remembers
- **Core Mission** — domains covered, with sub-domains
- **Critical Rules** — 10+ detailed rules (e.g., "never provide legal advice", "flag everything")
- **Deliverables** — structured templates ready to fill
- **Workflow** — step-by-step process per task type
- **Communication Style** — how the agent talks

## How It Differs from SOUL.md

| Agency-Agents .md | SOUL.md (Hermes profile) |
|---|---|
| Rich personality + detailed rules | Concise personality + workflow |
| No tools (just text) | Full tool access (terminal, file, web) |
| No memory | EVOLUTION.md + Hindsight |
| No routing | Model routing per task type |
| No execution | Real execution + verification |
| Static (never changes) | Self-improving (EVOLUTION.md) |

## Fusion Pattern

When activating a new profile or enriching an existing one:

1. Pick the most relevant agent from `_library/`
2. Extract: identity, critical rules, deliverable templates
3. Fuse into SOUL.md with: model routing, tool access, Hermes-specific rules
4. Keep it concise — the full .md is 3-5KB, truncate to ~2KB for SOUL.md

## Most Useful Agents for Tech Projects

| Agent | Division | Use for |
|---|---|---|
| engineering-senior-developer | engineering | Full-stack coding |
| engineering-backend-architect | engineering | API, database, architecture |
| engineering-frontend-developer | engineering | UI, React, CSS |
| engineering-security-engineer | engineering | Auth, webhooks, security review |
| engineering-devops-automator | engineering | CI/CD, deploy, infrastructure |
| engineering-sre | engineering | Monitoring, incidents |
| design-ui-designer | design | Visual design, components |
| specialized-legal-document-review | specialized | Contract review, compliance |
| specialized-compliance-auditor | specialized | SOC2, ISO27001 |
