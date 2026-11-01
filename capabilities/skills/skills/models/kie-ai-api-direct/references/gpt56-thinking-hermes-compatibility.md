# Kie GPT-5.6 — thinking et compatibilité Hermes

## Source observée

Page Kie.ai GPT-5.6 : `https://kie.ai/gpt-5-6?model=gpt-5-6-sol`.

Le Playground affiche un sélecteur de raisonnement : `Low`, `Medium`, `High`, `XHigh`. La page mentionne aussi `max` et `ultra` dans le texte promotionnel, mais ne définit pas leur représentation JSON.

## Contrat API publié par la page

La page documente :

```bash
curl -X POST https://api.kie.ai/codex/v1/responses \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer ***' \
  -d '{"model":"gpt-5-6-luna","stream":true,"input":[{"role":"user","content":[{"type":"input_text","text":"Hello!"}]}],"tools":[]}'
```

Points importants :

- endpoint **Responses-style**, pas `/chat/completions` ;
- le modèle est un identifiant Kie (`gpt-5-6-luna`, `gpt-5-6-terra`, `gpt-5-6-sol`) ;
- `stream` et `tools` sont montrés ;
- la page parle de callback ou de polling par Task ID ;
- aucun champ `thinking`, `reasoning_effort` ou `reasoning.effort` n’est spécifié dans l’exemple ni dans le guide extrait.

Conclusion : le thinking est sélectionnable dans le Playground, mais son contrôle programmatique n’est **pas contractuellement confirmé**. Ne pas prétendre qu’un champ OpenAI standard fonctionne sans interception ou smoke test facturé.

## Compatibilité Hermes vérifiée (v0.18.2 — rerun 2026-07-10)

Sur Hermes Agent v0.18.2, `hermes_constants.parse_reasoning_effort()` accepte :

- `minimal`, `low`, `medium`, `high`, `xhigh`, `max` ;
- `none` pour désactiver le raisonnement.

**Correction (v0.18.2, testé) :** Contrairement à l'analyse antérieure, Hermes v0.18.2 **préserve** le format `codex_responses` pour l’URL `https://api.kie.ai/codex/v1`. Le payload envoyé est correct : `POST /codex/v1/responses` avec les champs `input`, `tools`, `reasoning` au format Responses. Le resolver ne downgrade PAS vers `chat_completions`.

**Blocage réel (HTTP 403) :** L'appel Hermes échoue avec `HTTP 403: Your request was blocked` parce que le **User-Agent browser-like est absent**. Les appels Python directs avec `User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36` passent. Hermes n'ajoute pas d'UA pour les providers custom `codex_responses`.

**Deuxième problème :** Le `reasoning_effort: max` configuré dans `config.yaml` n'est PAS propagé dans le payload. Le dump de requête Hermes montre `reasoning: {effort: medium, summary: auto}` — la valeur par défaut. Le mapping config→payload ne fonctionne pas pour le mode `codex_responses`.

**`billing_provider` et `billing_base_url`** sont null dans `state.db` après l'échec 403 — pas de fallback activé.

## Format du champ reasoning (confirmé par smoke test)

Les appels directs confirment le contrat du champ `reasoning` :

- ✅ `"reasoning": {"effort": "max"}` — accepté, retourne `reasoning_tokens > 0`
- ❌ `"reasoning_effort": "max"` (flat, style OpenAI Chat Completions) — provoque une erreur serveur HTTP 200 + body `code: 500, Server exception` ; Kie n'accepte que le format nested
- Le sous-objet `reasoning` accepte `effort`, `mode`, `context`, `summary` en lecture ; seul `effort` a été testé en écriture

## Voies d'intégration

1. **Rustine pour le 403 :** injecter `User-Agent: Mozilla/5.0 ...` dans l'adaptateur `codex_responses` pour les URLs `api.kie.ai`. Voir `references/hermes-runtime-403-repair.md` pour le pattern côté Claude (même problème, même solution).
2. **Rustine pour le reasoning_effort :** propager `reasoning_effort` du config vers `reasoning.effort` (nested) dans le payload Responses — ne jamais utiliser le champ plat `reasoning_effort` que Kie rejette.
3. **Ne pas faire :** utiliser `reasoning_effort` comme champ plat ou supposer que Kie accepte le format Chat Completions.
