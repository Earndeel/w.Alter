# Voice Router Only Pattern — Gemini Live Tool Architecture

## Problem (2026-05-18)

Gemini Live had direct access to `get_inbox_digest` and `get_beeper_conversation` tools alongside `voice_router`. When the user asked to "check my latest Beeper messages", Gemini Live used the direct tools instead of routing through `voice_router` → Hermes. This bypassed the orchestrator model entirely.

The user had to insist multiple times before Gemini Live called `voice_router`, and by then the `user_utterance` contained the correction ("Non non, il y a un problème là...") instead of the original request.

## Solution

1. **Remove all direct data tools from Gemini Live.** Only keep: `voice_router`, `ping_tool`, `get_runtime_info`, proactive subscription tools.
2. **Rewrite system prompt** to route ALL requests through `voice_router`.
3. **Inject verbatim user utterance** via `normalizeToolCallArgs`.

## System Prompt Template

```
Tu es W.Alter, la couche vocale temps réel de Monsieur.

RÈGLE ABSOLUE — TU N'AS AUCUN ACCÈS direct aux données personnelles de Monsieur.
Tu n'as qu'UN SEUL outil pour agir: voice_router. Tout le reste est géré par le cerveau profond (Hermes) derrière voice_router.

ROUTAGE — OBLIGATOIRE pour TOUTE demande qui n'est pas du small talk pur:
- TOUT ce qui touche données personnelles, messages, Beeper, emails, mémoire, web, système, code, fichiers, action externe, ou décision: appelle voice_router immédiatement.
- voice_router décide la meilleure route (réponse directe rapide OU escalade Hermes).
- Quand tu appelles voice_router, passe TOUJOURS user_utterance = la phrase EXACTE de Monsieur, mot pour mot. Ne reformule JAMAIS la demande de Monsieur dans user_utterance.
- Si l'outil risque de prendre plus d'une seconde, dis d'abord une micro-phrase de prise en charge: "Je vérifie, Monsieur." ou "Je m'en occupe, Monsieur." Puis appelle l'outil.

Tu peux répondre SANS voice_router UNIQUEMENT pour:
- salutations pures ("bonjour", "ça va")
- small talk évident ("il fait beau", "c'est quelle heure")
- reformulation, aide à formuler une phrase

APRÈS RETOUR DE voice_router:
- Si spoken_response non vide: dis-le à voix haute immédiatement, naturellement, dans ton style butler. 1-2 phrases max.
- Si job_id présent (hermes_async): dis le spoken_response (accusé de réception), puis le résultat arrivera automatiquement. Pas besoin de surveiller.
- Si une clarification est demandée: pose la question à Monsieur naturellement.
```

## Tool Registration (app.js)

```js
// ONLY these tools — no get_inbox_digest, no get_beeper_conversation
client.addFunction(new PingTool());
client.addFunction(new RuntimeInfoTool(runtimeInfo));
client.addFunction(new VoiceRouterTool());
client.addFunction(new ProactiveStatusTool());
client.addFunction(new CreateProactiveSubscriptionTool());
client.addFunction(new ListProactiveSubscriptionsTool());
client.addFunction(new DeleteProactiveSubscriptionTool());
```

## normalizeToolCallArgs (app.js)

```js
function normalizeToolCallArgs(name, args = {}) {
  const normalized = { ...(args || {}) };
  const utterance = state.lastUserTranscript || state.partialUserTranscript || normalized.original_request || normalized.user_utterance || normalized.query || "";

  // For voice_router: always inject the user's verbatim utterance
  if (name === "voice_router") {
    if (utterance && !normalized.user_utterance) normalized.user_utterance = utterance;
    if (utterance && !normalized.query) normalized.query = utterance;
  }

  return normalized;
}
```

## Lessons Learned

- Gemini Live will ALWAYS prefer a direct tool over a routing tool if both are available.
- The system prompt instruction "use voice_router for X" is NOT sufficient if a direct tool for X also exists.
- The only reliable way to force routing through Hermes is to remove the direct tools entirely.
- `user_utterance` must be injected client-side from `state.lastUserTranscript` — Gemini Live may reformulate the request before passing it to the tool.
