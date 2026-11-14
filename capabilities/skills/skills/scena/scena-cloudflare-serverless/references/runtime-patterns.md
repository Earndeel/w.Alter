## Key Patterns

### Multi-Tenant Webhook Routing
Each client's Telegram bot webhook points to `https://api.walter-ai.cloud/webhook/telegram/{matricule}`. The Worker looks up the client in D1 by matricule. Bot token never leaves D1.

### Zero-Storage Media Proxy
Telegram URLs contain the bot token (security risk). Solution: proxy route `/proxy/media/{file_id}?client={matricule}`.
- Worker looks up client's bot token from D1
- Calls Telegram getFile → streams response directly
- No files stored anywhere
- PiAPI receives `https://api.walter-ai.cloud/proxy/media/xxx?client=sc0001` — token hidden

### PiAPI Webhook Async Flow (Free Tier — No Queues)
1. Client sends message → Worker creates job in D1 (status=processing)
2. Worker submits to PiAPI with `config.webhook_config.endpoint = https://api.walter-ai.cloud/webhook/piapi`
3. Worker responds 200 to Telegram immediately ("Rendu en cours 🍿")
4. PiAPI finishes → hits `/webhook/piapi` → Worker sends result to Telegram

### Agent Brain (State Machine)
States: `idle`, `waiting_image`, `waiting_video`, `waiting_voice`, `consulting`

### Admin-manageable orchestration layer (style presets + action routes)
To avoid hardcoding all creative logic in `tools.ts`, add two D1-backed control-plane tables and expose them in the admin dashboard:

- `style_presets`
  - slug, title, description
  - `image_prompt_template`, `video_prompt_template`
  - `negative_prompt`, `tags_json`, priority
  - examples: `cinematic`, `ugc`, `thumbnail`, `product-shot`, `lifestyle`

- `action_model_routes`
  - id, `action_type` (`image_gen`, `video_gen`, `resize_image`, ...)
  - provider, model_id, endpoint
  - `default_style_slug`, `params_json`, priority
  - examples:
    - `image_gen` → `fal-ai/nano-banana-2`
    - `video_gen` → `seedance-2-fast`

Runtime precedence should be:
1. workflow step overrides (`model_provider`, `model_id`, `params_json.style_preset_slug`)
2. global `action_model_routes` default for the action type
3. built-in fallback in code

This lets the agent choose a high-level action while the Worker injects the right model + prompt preset into the provider payload.

D1 columns on `clients` table:
- `state TEXT DEFAULT 'idle'`
- `context TEXT DEFAULT '[]'` — JSON array of conversation messages
- `summary TEXT DEFAULT ''` — compacted project summary
- `portfolio TEXT DEFAULT '[]'` — archived validated media URLs

System prompt enforces bifurcation: vague → consult (text only), specific → execute (tool call).

### Telegram conversation policy (production-safe)
For Scena's Telegram UX, don't let the agent jump straight to generation on every clear request. Use a guided intake layer before the free-form agent when the user starts a project.

## Prompt Injection Middleware (PRE_PROMPTS_DICTIONARY)

L'agent Mimo génère un payload minimaliste (`prompt` = sujet court + `style`). Le Worker intercepte et injecte la "recette qualité agence" avant l'envoi à PiAPI/Fal.ai.

```typescript
// tools.ts — Dictionary de 6 styles
export const PRE_PROMPTS_DICTIONARY: Record<string, PrePromptEntry> = {
  cinematic: { image_prompt: "...{SUBJECT}...", video_prompt: "...{SUBJECT}...", negative_prompt: "..." },
  ugc: { ... },
  minimalist: { ... },
  product_shot: { ... },
  lifestyle: { ... },
  dramatic: { ... },
};

// Injection function
export function injectPrePrompt(style: string, subject: string, mediaType: "image" | "video") {
  const entry = PRE_PROMPTS_DICTIONARY[style] || PRE_PROMPTS_DICTIONARY["cinematic"];
  const template = mediaType === "image" ? entry.image_prompt : entry.video_prompt;
  return { prompt: template.replace(/\{SUBJECT\}/g, subject), negative_prompt: entry.negative_prompt };
}

// Usage in agent.ts — toolGenerateImage / toolGenerateVideo
const injected = injectPrePrompt(args.style || "cinematic", args.prompt, "image");
const falPayload = { prompt: injected.prompt, negative_prompt: injected.negative_prompt, ... };
```

**Pattern**: Mimo (LLM) = décide QUOI + STYLE. Worker (code) = injecte COMMENT (qualité). Sépare raisonnement et craft.
