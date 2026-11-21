# AA Free-Tier API — Integration du Watchdog

## Endpoint

```
GET https://artificialanalysis.ai/api/language/models/free
```

- **Authentification** : Header `x-api-key` (PAS `Authorization: Bearer`). La clé est stockée dans le vault sous `artificial-analysis/api_key`.
- **Format réponse** : JSON, paginé. Chaque page retourne au maximum 200 modèles.
- **Pagination** : Le endpoint retourne les champs `page`, `pageSize`, `totalPages`, `totalItems`.
  Pour récupérer toutes les pages : incrémenter `?page=N` jusqu'à `totalPages`.
- **Volume** : ~507 modèles sur 3 pages (200 + 200 + 107) sur le tier gratuit.

## Champs pertinents par modèle (dans `items[]`)

| Champ JSON | Signification |
|---|---|
| `slug` | Identifiant unique du modèle (ex: `kimi-k2.6`) |
| `name` | Nom lisible (ex: `Kimi K2.6`) |
| `creator.name` | Créateur (ex: `Moonshot AI`) |
| `medianOutputTokensPerSecond` | Vitesse en tok/s |
| `qualityMetrics.artificialAnalysisIntelligenceIndex` | **Score AA d'intelligence** (0-100) — le champ critique pour le watchdog |
| `contextWindow` | Fenêtre de contexte en tokens |
| `pricing.perMillionInputTokens` | Prix input ($/1M tokens) |

## 3 pages de fetch (recommandé)

```bash
AA_KEY=$(vault get artificial-analysis/api_key)
for page in 1 2 3; do
  curl -s "https://artificialanalysis.ai/api/language/models/free?page=$page&pageSize=200" \
    -H "x-api-key: $AA_KEY" > /tmp/aa_page${page}.json
done
```

## Modèles Frontière (AA >= 46) — snapshot live Juin 2026

Ces scores changent — toujours se fier à l'API live, pas à ce fichier. Donné à titre indicatif pour le seuil `AA >= 46` :

| Modèle | Créateur | Score AA | Tok/s | Contexte | Prix input/M |
|--------|----------|----------|-------|----------|-------------|
| kimi-k2.6 | Moonshot AI | 53.9 | 68 | 262k | $0.49 |
| mimo-v2.5-pro | Xiaomi | 53.8 | 89 | 32k | $1.50 |
| mimo-v2.5 | Xiaomi | 48.0 | 121 | 32k | $0.79 |
| deepseek-v4-flash | DeepSeek | 46.5 | 112 | 1M | $0.18 |
| qwen3-coder-480b-a35b | Qwen Team | ~46.5 | ~50 | 262k | ~$0.20 |

**Modèles open-weight qui approchent (44-45) :**
- nemotron-3-ultra-550b — AA 47.7 (NVIDIA, nouveau)
- gpt-oss-120b — AA ~45.8 (Cerebras)
- qwen3-6-plus-instruct — AA ~44.7 (Qwen Team)

## Différences constatées avec `aa_benchmarks_ref.md` (Juin 2026)

Le fichier statique contient des scores qui divergent significativement de l'API live :

| Modèle | Fichier statique (scores) | API live (scores) |
|--------|--------------------------|-------------------|
| Qwen3 Coder 480B | ~45 (pas dans le fichier) | ~46.5 |
| GPT-OSS 120B | ~45 | ~45.8 |
| Llama 3.3 70B | ~36 | ~34.0 |
| Gemma 4 31B | ~39 | ~39.2 (proche) |
| Nemotron 3 Ultra 550B | absent | 47.7 |

**Conclusion : le fichier statique est dépassé de 2-5 points sur plusieurs modèles.** L'API live est la source de vérité.

## Pitfall : pagination obligatoire

Une erreur fréquente est de ne récupérer que les ~25 premiers modèles de la page 1. La page 1 contient surtout des micro-modèles (Nemotron 8B, Dolphin, Phi) triés par défaut. Les modèles frontière (AA >= 46) comme Kimi K2.6 arrivent souvent page 2 ou 3. **Toujours itérer les 3 pages** pour avoir la couverture complète.
