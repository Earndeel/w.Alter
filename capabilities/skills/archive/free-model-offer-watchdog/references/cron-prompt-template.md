# Cron Prompt Template for AI Free Offers Watchdog

Current working prompt as of 2026-05-28 (v8).

## Working Prompt

```
Tu es un assistant de veille IA. Lis le fichier `/tmp/free_offers_raw.json` produit par le collecteur v8.

Le JSON contient des items avec : model_id, name, provider, description, context_length, max_completion, modalities, link.

Étapes :
1. Lis le JSON avec `cat /tmp/free_offers_raw.json`
2. Pour chaque item, vérifie le score AA dans `~/.hermes/scripts/aa_benchmarks_ref.md` (seuil >= 46)
3. Si le modèle n'est pas dans les benchmarks, vérifie via x_search "model_name artificial analysis intelligence index" — ne l'exclue pas sans vérifier
4. Construis le rapport FILTRÉ (pas la liste complète) :
   - Modèles AA >= 46 en premier (triés par score décroissant)
   - Modèles notables non-benchés en section "Notables" (multimodal, thinking, grande ctx)
5. Envoie via Telegram (vault get telegram/bot_token) — split si > 4000 chars
6. Après l'envoi, réponds [SILENT]
```

## Iteration History

| Version | Problem | Fix |
|---------|---------|-----|
| v1-v5 | Various (regex, noise, dedup, placeholders, double delivery) | → agent mode, filters, curl+silent |
| v6 | Missed GitLawb/MiMo, Nitter dead | → OpenRouter API primary, AA >= 46 |
| v7 | Descriptions="?", links with :free, Nitter 0 results | → v8 collector: descriptions, clean links, Nitter removed |
| v8 | Missing Kimi K2.6 (AA 54) from benchmarks, no tri, msg too long | → verify unknown scores via x_search, strict AA filter, split msgs |

## Anti-Patterns

1. **Don't send full list** — filter by AA >= 46, only include notables separately
2. **Don't trust benchmarks blindly** — verify unknown models via x_search before excluding
3. **Don't send > 4096 chars** — Telegram rejects with 400 Bad Request
4. **Don't use parse_mode=Markdown** — emojis + URLs mix = broken parsing
5. **Don't let agent re-run collector** — it runs at 23h45 UTC separately
6. **Don't set AA threshold below 46** — models below are too weak for Hermes
7. **Don't let cron auto-deliver** — use curl + `[SILENT]` to avoid metadata wrapper
8. **Don't use placeholder text in curl** — construct the message properly
