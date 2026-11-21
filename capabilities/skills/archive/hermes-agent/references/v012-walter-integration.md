# v0.12.0 W.Alter Integration Notes

Session: 2026-05-04. Hermes v0.12.0 (2026.4.30) installed at /root/.hermes/hermes-agent, 1 commit behind main.

## Local Modifications Audit (pre-update checklist)

Before any `hermes update`, check git status in the source tree:

```bash
cd /root/.hermes/hermes-agent
git status --short
git diff --stat
```

On this date, W.Alter had 6 modified files + 5 untracked. The modified files were smart-threshold compression patches and TTS robustness fixes. The untracked files included:

- `agent/super_coder_autoroute.py` — custom auto-routing logic for coding requests
- `tests/agent/test_smart_model_task_routing.py` — tests for ordered task-specific routing
- `plugins/memory/lancedb_gemini/` — custom memory backend using LanceDB + Gemini embeddings
- `docs/plans/` — planning documents

**Workflow:** stash modifiés → update → stash pop → résoudre conflits si besoin.

## W.Alter Profile Setup

| Profile | Model | Usage |
|---------|-------|-------|
| `default` | kimi-k2.6 (OpenCode Go) | Ordonnanceur général, gateway Telegram actif |
| `coder` | anthropic/claude-sonnet-4 | Code, architecture, auth, billing, webhooks |
| `research` | kimi-k2.6 | Recherche, veille, benchmark |

Gateway: Telegram uniquement (`@walter_0002_bot`). Pas de Kanban initialisé à ce jour.

## Kanban Integration Pattern pour Scena

Workflows type que le dispatcher Kanban peut orchestrer avec les profils existants :

1. **Brief créatif → Livraison**
   - `default` écrit spec → `research` storyboard/prompts → `coder` génère MP4 → review gate → `default` upload R2

2. **Veille modèles**
   - `research` scanne 5 sources (parallèle) → `default` synthétise → récap Telegram

3. **Hotfix prod**
   - `coder` corrige → review gate (Lucas) → `default` deploy

Config Kanban suggérée :

```yaml
kanban:
  dispatch_in_gateway: true
  default_workspace_kind: dir:/root/scena-work
  notify_platform: telegram
  reclaim_stale_seconds: 300
  max_runtime_seconds: 1800
```

## v0.12.0 Features Relevant to W.Alter

- **Kanban durable** — SQLite kernel, WAL mode, dispatcher intégré au gateway
- **Curator** — maintenance auto des skills, grade/prune/consolide
- **Subagent cost rollup** — coûts delegate_task remontés dans session parent
- **4 nouveaux providers inference**
- **TUI cold start -57%**

## Credentials State (session snapshot)

- OpenRouter : provisionné
- OpenAI Codex OAuth : actif (image gen possible sans clé API)
- Nous Portal : refresh révoqué
- Anthropic : non configuré (mais utilisé via OpenRouter pour coder)
- Fal : épuisé (image gen bascule sur openai-codex)
