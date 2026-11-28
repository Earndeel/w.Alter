---
name: free-model-offer-watchdog
description: Monitor free AI model offers via OpenRouter API — LLM-powered filtering with AA benchmark validation, Telegram delivery.
version: 8.0.0
metadata:
  hermes:
    tags: [monitoring, free-models, providers, openrouter, cron]
---

# Free Model Offer Watchdog

Pipeline : OpenRouter API (source de vérité) + providers externes → collecteur Python avec cross-ref AA automatique → agent LLM avec tri AA → rapport Telegram filtré.

## Architecture

- **Cron collecteur** `AI Offers Collector` (0df8c3abe3fd) — 23h45 UTC, no_agent, script `ai_offers_scanner.py` v8
- **Cron agent** `AI Free Offers Watchdog` (eb00a14590b4) — 0h UTC, agent mode, delivery Telegram (= 7h Bangkok)
- **Script** `~/.hermes/scripts/ai_offers_scanner.py` (v8 — API AA live)
- **Output** `/tmp/free_offers_raw.json`
- **AA API** `https://artificialanalysis.ai/api/v2/language/models/free` — clé dans vault `artificialanalysis/api_key`
- **Benchmarks** `~/.hermes/scripts/aa_benchmarks_ref.md` (cache de secours, plus utilisé en direct)
- **Benchmarks — fichier statique (fallback)** `~/.hermes/scripts/aa_benchmarks_ref.md` (seuil AA >= 46). N'utiliser QUE si l'API live est injoignable.
- **Delivery** Telegram channel 1146774717 (bot token via `vault get telegram/bot_token`)

## Rapport : TRI OBLIGATOIRE

L'agent ne doit JAMAIS envoyer la liste complète des modèles. Il doit :
1. Lire `aa_benchmarks_ref.md` et ne garder que les modèles avec AA >= 46
2. Ajouter les modèles non-benchés mais notables (multimodal, thinking, grande ctx) en section "Notables"
3. Trier : multimodal d'abord, puis par score AA décroissant
4. Envoyer via Telegram en gérant la limite 4096 chars (split si nécessaire)

## Pipeline

1. Agent à 0h UTC : lance le collecteur `python3 ~/.hermes/scripts/ai_offers_scanner.py`
2. Collecteur : OpenRouter API + check providers externes → cross-ref avec **AA API live** (`/language/models/free`, pagination 3 pages) pour évaluer les scores. Fallback sur `aa_benchmarks_ref.md` si API injoignable.
3. Protection rate-limit : jamais écraser un JSON avec moins de résultats
4. Agent lit le JSON, filtre AA >= 46, signale les modèles sans score AA
5. Tri : multimodal d'abord, puis score AA décroissant, puis ctx décroissant
6. Envoie 3 messages Telegram (résumé + frontier + alertes AA manquants) → répond `[SILENT]`

### Source AA : API Artificial Analysis (live, primaire)
- `GET https://artificialanalysis.ai/api/v2/language/models/free`
- Header `x-api-key: $AA_API_KEY` (vault `artificialanalysis/api_key`)
- Gratuit : 1000 req/jour, 507 modèles, 498 avec score Intelligence Index
- Retourne `evaluations.artificial_analysis_intelligence_index` (float)
- Matching : table manuelle OpenRouter slug → AA slug, avec fallback heuristique
- Si API indisponible → fallback fichier `aa_benchmarks_ref.md`

### Source 1 : OpenRouter API (primaire, fiable)
- `GET https://openrouter.ai/api/v1/models` → filtre `:free`
- Données CERTAINES : le modèle est vraiment gratuit, prix = $0
- ~23 modèles gratuits permanents
- Champs extraits : `description`, `modalities`, `context_length`, `max_completion`
- Lien format `https://openrouter.ai/{id_sans_:free}`
- Voir `references/openrouter-free-models.md` pour la structure de réponse

### Source 2 : Providers externes (GitLawb, etc.)
- Vérification npm registry pour GitLawb OpenGateway
- Détection de nouvelles versions

## Report Format (filtré AA >= 46)

Le rapport ne contient QUE les modèles passant le seuil AA >= 46, plus les "notables" non-benchés.

```
🤖 Veille IA Gratuite — [date]

[N modèles gratuits scannés, X passent le filtre AA ≥ 46 :]

▸ [emoji si multimodal/thinking] [Modèle] (AA: [score])
  [Description courte]
  🔗 [lien provider]

[Si notables :]
Les N autres sont sous le seuil (AA < 46). Notables quand même :
▸ [Modèle] (~[score estimé]) — [point fort]
```

Liens provider :
- OpenRouter → `https://openrouter.ai/[model-id-sans-:free]`
- GitLawb → `https://www.npmjs.com/package/@gitlawb/openclaude`
- Nous Portal → `https://nousresearch.com`
- freebuff → `https://www.npmjs.com/package/freebuff`

## Manual Run

```bash
python3 ~/.hermes/scripts/ai_offers_scanner.py
cat /tmp/free_offers_raw.json | python3 -m json.tool | head -50
```

## Support Files

- `references/telegram-report-delivery.md` — Telegram report split pattern, vault-secured token retrieval, 4096 char limit handling.
- `references/chinese-api-relay-landscape.md` — Chinese API relay services for frontier models: categories (legitimate relay, grey market, stolen keys), legitimate Chinese providers for open-source models (SiliconFlow, DeepSeek, etc.), decision framework for choosing between official API vs relay services.
- `references/openrouter-free-models.md` — OpenRouter API response structure for free models.
- `references/kimi-k26-free-real-world.md` — Kimi K2.6 :free real-world benchmarks: speed (41-68 tok/s), rate limits (~50 req/day free), retry behavior, vs Gemini Flash Lite comparison. Use when evaluating Kimi for any free-tier use case.

## Pitfalls

### Cron delivery doubling (CRITIQUE)
Si le prompt dit à l'agent d'envoyer via curl ET que le cron a `deliver: telegram:...`, le message arrive 2 fois : une propre via curl, une avec "Cron job response, Job ID:..." via l'auto-delivery. **Solution** : l'agent envoie via curl puis répond `[SILENT]` pour supprimer l'auto-delivery. Ne jamais laisser l'agent produire un rapport comme réponse finale si le cron livre sur Telegram.

### Nitter est mort
Nitter (nitter.net et instances alternatives) est down/bloqué depuis 2025+. Ne PAS l'utiliser comme source de données. Pour la veille X/Twitter, utiliser `x_search` (xAI) ou le skill `xurl`/`xitter`. Le collecteur v8 a supprimé Nitter et utilise OpenRouter API + npm registry pour les providers externes.

### USER.md = source de vérité pour le profil
Avant de répondre sur des infos utilisateur (timezone, localisation, préférences), vérifier le USER.md (`~/.hermes/memories/USER.md`) EN PREMIER. Ne jamais faire confiance à Hindsight seul — les entrées peuvent être périmées. Si Hindsight et USER.md divergent, USER.md prime, corriger Hindsight ensuite.

### Vérifier la qualité des données du collecteur
Après modification du collecteur, toujours auditer le JSON de sortie : descriptions remplies, liens valides (sans `:free` dans les URLs), modalités extraites. Comparer `count` vs scan précédent. Un collecteur qui produit des "?" partout est un collecteur inutile.
### L'agent lance le collecteur
Depuis v8, l'agent cron lance le collecteur lui-même (`python3 ~/.hermes/scripts/ai_offers_scanner.py`) puis lit le JSON produit. Le cron séparé `AI Offers Collector` est un backup/historique — l'agent est autonome.

### OpenRouter API = source de vérité
L'API OpenRouter retourne directement les modèles `:free` avec leurs prix ($0), descriptions, et modalités. C'est la source unique de vérité. GitLawb est vérifié via npm registry.

### Liens provider, pas liens tweets
L'utilisateur veut le lien vers le provider (OpenRouter, npm, site du provider), PAS le lien du tweet source. Le tweet sert uniquement de preuve/détection.

### GitLawb crédits cycliques — disponibilité intermittente
GitLawb OpenGateway liste des modèles comme "gratuits" (AA 54 via MiMo 2.5 Pro), mais son crédit OpenRouter s'épuise et se recharge cycliquement. Le collecteur détecte la présence du package npm mais ne teste pas l'endpoint réel. Conséquence : un modèle listé dans le rapport peut retourner 402 (crédits insuffisants) si on tente de l'utiliser. **Solution** : dans le rapport, si GitLawb est listé comme source externe, ajouter un disclaimer "⚠️ Disponibilité variable — crédits limités" à côté de son entrée. Le vérifier manuellement si le modèle est critique :
```bash
curl -s https://opengateway.gitlawb.com/v1/xiaomi-mimo/chat/completions \
  -H "Authorization: Bearer $GITLAWB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"mimo-v2.5-pro","messages":[{"role":"user","content":"ping"}],"max_tokens":2}' | grep -q "choices" && echo "✅ OK" || echo "❌ 402"
```

### Seuil AA >= 46
Le seuil est à 46 (pas 35). En dessous, les modèles sont trop faibles pour Hermes agent/coding. Mettre à jour `aa_benchmarks_ref.md` quand de nouveaux modèles sortent.

### Telegram 4096 char limit
Un rapport complet avec 24 modèles dépasse la limite Telegram (4096 chars). **Solution** : le rapport est déjà filtré (AA >= 46 + notables), ce qui le réduit à ~5-8 modèles. Si ça dépasse quand même, split en 2 messages : "Top picks" puis "Autres". Ne jamais envoyer un message > 4096 chars — Telegram renvoie 400 Bad Request.

### Benchmarks AA incomplets — CROSS-REF AUTOMATIQUE VIA API LIVE
**Le fichier `aa_benchmarks_ref.md` est systématiquement dépassé.** Les scores AA changent toutes les semaines. Depuis Juin 2026, l'API `/language/models/free` est disponible et fonctionnelle avec la clé gratuite Artificial Analysis.

**Nouvelle priorité :**
1. **APPEL API LIVE** → `GET /language/models/free` (pagination 3 pages) → obtient les scores AA de TOUS les modèles gratuits
2. Cross-ref entre les modèles OpenRouter `:free` et les scores live
3. Si l'API est injoignable (timeout, 401), **seulement là** utiliser le fichier statique `aa_benchmarks_ref.md`

Le collecteur v8 fait automatiquement le cross-ref à chaque run et signale les modèles sans score AA dans la sortie. Si un modèle n'est pas dans l'API ni le fichier, vérifier son score via `x_search` ou artificialanalysis.ai avant de l'exclure du rapport.

Voir `references/aa-free-api-integration.md` pour la procédure détaillée de fetch et pagination.

### Fichier benchmarks : format pipe obligatoire
Les entrées du fichier `aa_benchmarks_ref.md` doivent utiliser le format `model_id | nom | score | ctx | verdict` avec des pipes. Les lignes en commentaire (`#`) ne sont PAS parsées par le collecteur. Les offres spéciales (GitLawb, Nous Portal) doivent être ajoutées comme entrées pipe, pas comme commentaires.

### Ne PAS envoyer la liste complète
Le rapport ne doit contenir QUE les modèles AA >= 46. Ne jamais envoyer les 24 modèles "pour info" — c'est du bruit. Le tri est : frontier d'abord, puis alertes sur les manquants AA.

### Le template curl doit être construit par l'agent
Ne pas mettre `MESSAGE_ICI` comme placeholder dans le template curl — l'agent copie le texte littéralement. Lui dire de CONSTRUIRE le message et de l'envoyer via un here-doc ou une variable.
