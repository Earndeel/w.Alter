---
name: model-id-lookup
description: "Vérifier et résoudre un model ID sur OpenRouter avant utilisation. Jamais de substitution silencieuse."
version: 1.0.0
author: W.Alter
triggers:
  - model lookup
  - verify model
  - check model id
  - model not found
  - model substitution
metadata:
  hermes:
    tags: [openrouter, model, validation, delegation]
---

# Model ID Lookup & Validation

## Quand utiliser
- L'utilisateur demande un modèle spécifique (ex: "gemini 3.1 pro", "claude sonnet 4", "o3")
- Avant tout `delegate_task` avec per-task model override
- Avant tout `cronjob` avec model override
- Quand un modèle retourne une erreur (402, 404, model not found)

## Workflow OBLIGATOIRE

### Étape 1 : Lookup API OpenRouter
TOUJOURS vérifier l'ID exact via l'API AVANT d'utiliser un modèle.

```python
import requests, os

def lookup_model(query: str) -> list:
    """Cherche un modèle sur OpenRouter par nom partiel."""
    r = requests.get("https://openrouter.ai/api/v1/models", headers={
        "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}"
    })
    models = r.json().get("data", [])
    query_lower = query.lower()
    matches = []
    for m in models:
        mid = m.get("id", "").lower()
        name = m.get("name", "").lower()
        if query_lower in mid or query_lower in name:
            pricing = m.get("pricing", {})
            matches.append({
                "id": m["id"],
                "name": m.get("name", ""),
                "pricing_prompt": pricing.get("prompt", "?"),
                "pricing_completion": pricing.get("completion", "?"),
            })
    return matches

# Exemple
matches = lookup_model("gemini 3.1 pro")
# → [{"id": "google/gemini-3.1-pro-preview", ...}]
```

### Étape 2 : Validation
- **0 match** → ERREUR. Dire à l'utilisateur : "Modèle '{query}' introuvable sur OpenRouter. Modèles disponibles similaires : {list}"
- **1 match** → Utiliser cet ID exactement
- **2+ matches** → Demander à l'utilisateur lequel (ou choisir le plus pertinent si la différence est évidente)

### Étape 3 : Utilisation
Passer l'ID exact au delegate_task/cronjob :
```json
{"model": {"model": "google/gemini-3.1-pro-preview", "provider": "openrouter"}}
```

## Règles ABSOLUES
1. **JAMAIS substituer un modèle** sans vérification API
2. **JAMAIS downgrader silencieusement** (2.5 pro → 2.5 flash)
3. **JAMAIS supposer un model ID** — toujours vérifier
4. Si un modèle échoue (402, 404), **vérifier le bon ID** avant de réessayer
5. Si crédits insuffisants, **informer l'utilisateur** et proposer des alternatives

## Erreurs courantes
| Message utilisateur | ID probable | ID réel à vérifier |
|---|---|---|
| "gemini 3.1 pro" | google/gemini-3.1-pro-preview | ✅ vérifié |
| "gemini 2.5 flash" | google/gemini-2.5-flash | ✅ vérifié |
| "claude sonnet 4" | anthropic/claude-sonnet-4 | ✅ vérifié |
| "gpt 4o" | openai/gpt-4o | ✅ vérifié |
| "o3" | openai/o3 | ✅ vérifié |

## Pitfalls
1. **OpenRouter crédits** : une erreur 402 n'est PAS un "model not found" — c'est un problème de crédits. Ne pas substituer pour autant.
2. **Modèles preview** : certains modèles ont "-preview" dans le nom (gemini-3.1-pro-preview). L'utilisateur dit "pro", le bon ID est "pro-preview".
3. **Cache** : la liste des modèles OpenRouter change régulièrement. Ne pas faire de cache local — toujours requêter l'API en temps réel.
4. **max_tokens** : certains modèles (Gemini Pro) ont des limites de max_tokens élevées qui peuvent dépasser les crédits disponibles. Vérifier les crédits AVANT de lancer.

## Resolve a Walter sub-agent Router poste after HTTP 400

- Distinguish a Router **poste** (the routing slot accepted by `subagent`) from an OpenRouter model ID. A name can pass the tool's syntax check and still be unknown to the Router. Do not guess from the task description or retry an unchanged HTTP 400.
- Query the live gateway's `/v1/models` through the Engine client. Use the client to handle authentication; do not print credentials. On Monsieur's VM, run:

```sh
cd /walter/core/engine
walter-python - <<'PY'
import asyncio
from walter_engine import config, llm

async def main():
    client = llm.Client(config.load())
    try:
        postes = await client.postes()
        if postes is None:
            raise SystemExit('Gateway poste discovery unavailable; check gateway health before choosing a poste')
        print('\n'.join(sorted(postes)))
    finally:
        await client.close()

asyncio.run(main())
PY
```

- Check the base poste against the list (for example, check `general` for `general/L2`); check the level suffix separately. If the tool returns a list of valid postes, pick a suitable one and retry the delegation with that value.
- If the error persists with a known poste, compare the failed tool arguments with a successful delegation. Inspect `walter_engine/tools/agents.py` for tool validation, `walter_engine/llm.py` for HTTP handling, and `/walter/cognition/router/llm/gateway.py` for the gateway's 400 cases. Correlate by time and trace in `/user/Lucas/logs/walter-llm.jsonl`; entries marked `skipped: hedged` are not evidence of the failing request.
- If changing validation, test that an invented poste is rejected immediately with the discovered choices, without a completion call. The regression test is `engine/tests/test_native_engine.py::test_subagent_on_an_invented_poste_is_refused_at_once_with_the_real_ones` under `/walter/core`.
