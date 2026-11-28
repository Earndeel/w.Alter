# Agent Exception Isolation Audit — Scena ReAct Loop

Audit réalisé 2026-07-28. Fichiers audités : `workers/api/src/agent.ts`, `tools.ts`, `workflow_runner.ts`, `index.ts`, `tests/worker-regressions.test.mjs`, `tests/workflow-runner.test.mjs`.

## Méthode générique : audit de boucle ReAct

Pour tout harness agent LLM avec pattern Reason→Act→Observe, la chaîne à auditer est :

1. **Parsing des tool_calls LLM** — le payload LLM est non déterministe. Vérifier que l'accès à `toolCall.function.name` et `JSON.parse(toolCall.function.arguments)` a une isolation try/catch.
2. **Dispatcher de tools** — chaque handler individuel peut lever une exception (DB, réseau, assertion). Le switch/case doit avoir un catch englobant.
3. **Boucle d'itération** — si la boucle collecte `toolResults` puis pousse dans `messages` **après** la boucle, toute exception dans un seul tool fait perdre TOUS les résultats du batch.
4. **Sauvegarde de contexte** — vérifier que `context.push(user)` et `context.push(assistant)` sont atomiques : si l'assistant n'est pas poussé après un crash, le contexte est corrompu.
5. **Remontée au caller** — tracer la propagation jusqu'au handler HTTP final. Un `handleAgentTurn` sans try/catch + un handler Telegram sans catch = silence radio pour l'utilisateur.

## Finding P0 — agent.ts:191-362

**Défaut** : Aucune isolation try/catch par tool call dans la boucle for du ReAct loop.

### Chaîne de crash

```
LLM → tool_call.function = null
  → agent.ts:194 : TypeError non attrapé
    → sortie immédiate de la boucle (lignes 339-353 ignorées)
      → messages[] corrompu
        → contexte agent irrécupérable au tour suivant
```

### Évidences fichier:ligne

| Ligne | Preuve |
|-------|--------|
| agent.ts:194 | `JSON.parse(toolCall.function.arguments \|\| "{}")` — crash si `toolCall.function` undefined |
| agent.ts:317 | `executeTool(...)` — pas de try/catch |
| agent.ts:797 | `toolCall.function.name` — second point de crash dans executeTool |
| agent.ts:191 | Boucle `for` sans try/catch englobant |
| agent.ts:339-353 | `messages.push(...)` post-boucle → résultats perdus |
| agent.ts:393-395 | `context.push(...)` post-boucle → corruption |
| index.ts:2165 | `handleAgentTurn(...)` sans catch → Worker 500 silencieux |
| index.ts:438-442 | Top-level catch → `json({error: e.message}, 500)` — l'utilisateur Telegram ne voit rien |

### Test de régression manquant

Aucun test n'injecte `toolCall.function: null`, `function: undefined`, ou `arguments` invalide. Les tests ReAct dans `worker-regressions.test.mjs:423` ne couvrent que le chemin nominal.

### Correctif minimal

```typescript
// agent.ts autour de la ligne 317 — wrapper chaque tool call
try {
  const result = await executeTool(env, clientId, matricule, toolCall, ...);
  toolResults.push(result);
} catch (e: any) {
  console.error(`ReAct tool ${toolCall.function?.name || 'unknown'} crashed:`, e.message || e);
  toolResults.push({
    success: false,
    error: String(e.message || 'internal_error'),
    telegram_message: 'Outil indisponible, je continue.',
  });
}
```

Et wrapper `JSON.parse` ligne 194 dans un try/catch avec fallback `{}`.

## Finding secondaire — Context compaction évince les gardes d'idempotence

**Fichier** : agent.ts:260-314 vs 397-408

Les gardes `generate_image`/`generate_video` (lignes 260-314) scannent le tableau `messages[]` en mémoire. Quand le contexte dépasse `MAX_CONTEXT_MESSAGES * 2 = 16` (ligne 397), il est compacté et remplacé par un résumé. Les appels précédents sont évincés → la garde ne voit plus rien → credit double-charge possible.

Ce risque est déjà listé dans SKILL.md sous "Same-turn parallel tool calls bypassing duplicate/approval checks that only inspect prior messages".
