---
name: pxpipe-planning-proxy
description: Architecture de planification pxpipe → Kie.ai Claude. Coût image FIXE (~2684 tokens) — remplir la page ou ne pas utiliser. Seuil rentabilité 9100 chars. Assembleur fill_page.py inclus.
category: devops
---

# pxpipe — Planning Proxy pour W.Alter

## ⚠️ Proxy Python dégradé = OBSOLÈTE

Le proxy `/root/pxpipe-openrouter/` (Python, 1568×728, 6 240 chars/page) est **déconseillé**. Il n'atteint que ~3 chars/token — quasiment aucun gain. Monsieur l'a explicitement rejeté.

Toujours utiliser le **vrai pxpipe de teamchong** (`/root/pxpipe/`, Node.js, 1568×1568, 48 000 chars/page, ~2 684 tokens/image). Ratio max théorique : **5,3×** (page pleine). Voir la table de performances ci-dessous pour les mesures réelles.

## Principe

```
┌──────────┐    Anthropic     ┌──────────────┐    Anthropic     ┌───────────┐
│  Hermes  │ ──────────────→  │    pxpipe    │ ──────────────→ │  Kie.ai   │
│  (ou CLI)│ ←──────────────  │ (localhost:  │ ←────────────── │  Claude   │
│          │   Messages API   │    47821)    │   Messages API  │  Fable 5  │
└──────────┘                  └──────────────┘                  └───────────┘
       │                              │
       │   System + Contexte          │   Render PNG 1568×1568
       │   (selon taille payload)     │   1 page = 48K chars = ~2 684 tokens
       │                              │   Ratio max : 5,3× (page pleine)
```

Le vrai pxpipe :
1. Accepte les requêtes au format Anthropic Messages API (comme l'API native)
2. Rend le `system` prompt en images PNG 1568×1568 (48 000 chars/image)
3. Forward **directement** à l'upstream Anthropic — pas de traduction Anthropic→OpenAI
4. Dashboard web pour monitoring live (`http://127.0.0.1:47821`)

## Installation & lancement

```bash
cd /root/pxpipe
pnpm install
```

### Lancement manuel (foreground debug)

```bash
cd /root/pxpipe
ANTHROPIC_UPSTREAM=https://api.kie.ai/claude \
  PXPIPE_MODELS="claude-fable-5,claude-opus-4-8" \
  npx tsx src/node.ts
```

### Lancement background (production)

```bash
cd /root/pxpipe
nohup bash -c 'ANTHROPIC_UPSTREAM=https://api.kie.ai/claude PXPIPE_MODELS="claude-fable-5,claude-opus-4-8" npx tsx src/node.ts' \
  > /tmp/pxpipe.log 2>&1 &
```

### Variables d'environnement clés

| Variable | Valeur | Description |
|---|---|---|
| `ANTHROPIC_UPSTREAM` | `https://api.kie.ai/claude` | **Kie.ai Claude endpoint** (pas api.anthropic.com) |
| `PXPIPE_MODELS` | `claude-fable-5,claude-opus-4-8` | Modèles à compresser (off = désactiver) |
| `PORT` | `47821` | Port d'écoute |
| `PXPIPE_DUMP_DIR` | `/tmp/pxpipe_dump` | Debug : sauvegarde les PNG générés |

## Appel depuis un client

```python
import urllib.request, json

body = {
    "model": "claude-fable-5",
    "max_tokens": 2000,
    "system": "Ton system prompt complet ici...",  # → pxpipe le rend en PNG
    "messages": [{"role": "user", "content": "Question"}]
}

req = urllib.request.Request(
    "http://127.0.0.1:47821/v1/messages",
    data=json.dumps(body).encode(),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {kie_api_key}",  # ⚠️ Bearer, PAS x-api-key
        "anthropic-version": "2023-06-01",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
)
```

## Pipeline Planner/Executor Fable 5 → Sonnet 5

Le lanceur de référence est `scripts/fable_pipeline.py` dans ce skill. Architecture vérifiée :

```text
Tâche + contexte explicite
  → Fable 5 via pxpipe/Kie.ai sur `127.0.0.1:47822`
  → contrat `PLAN_CONTRACT` validé strictement
  → Hermes `chat -q` isolé
  → `claude-sonnet-5` via `custom:kie-pxpipe`
  → vrais outils Hermes + rapport `EXECUTION_REPORT`
```

### Exécution complète

```bash
cd /root/.hermes/skills/devops/pxpipe-planning-proxy
python3 scripts/fable_pipeline.py run \
  --task-file /tmp/task.txt --workdir /tmp/fable-work \
  --plan-output /tmp/fable-plan.json \
  --report /tmp/fable-report.json \
  --usage-file /tmp/fable-usage.json
```

Garanties : modèle exact, aucune substitution silencieuse, `max_turns` injecté dans un `HERMES_HOME` temporaire, et clé Kie transmise seulement au processus enfant. Le proxy lancé par le script est le seul qu'il arrête.

Sur blocage majeur, `run` replannifie une fois. L'échec initial est conservé dans `report.replan-1.json`; l'usage initial dans `usage.attempt-1.json` et `usage.attempt-1.raw.txt`.

## Principe fondamental : coût image FIXE

**Le coût d'une page pxpipe (1568×1568) est fixe : ~2 684 tokens**, quel que soit le remplissage.
Une page à 10% (5K chars) coûte exactement le même prix qu'une page à 95% (47K chars).

**Conséquence : si on utilise pxpipe, on REMPLIT la page.** Sans quoi on paie l'image pour du vide.

### Arbre de décision texte vs pxpipe

```
payload ≤ 9 100 chars → TEXTE DIRECT (moins cher que l'image fixe)
payload > 9 100 chars → PXPIPE → remplir à 95%+ (47K chars) via fill_page.py
payload > 47 000 chars → PXPIPE multi-page → 1 page = ~2 684 tokens
```

Le point mort à 9 100 chars vient du calcul : 9 100 / 3.4 ≈ 2 684 tokens texte = 2 684 tokens image.

**ATTENTION :** le chiffre 5,8× est un maximum théorique (page pleine). En dessous de 30% de remplissage, le ratio tombe sous 1× et pxpipe COÛTE plus cher que le texte. Ce n'est pas un bug — c'est le coût fixe de l'image qui n'est pas amorti.

## Performances mesurées (2026-07-10, mis à jour)

Tests itératifs avec Fable 5 via pxpipe → Kie.ai :

| Taille payload | Fill | pxpipe tokens | Texte estimé | Ratio | Verdict |
|---|---|---|---|---|---|
| 5 392 chars | 11% | 1 831 | ~1 586 | 0.9× | ❌ pxpipe perdant |
| 7 493 chars | 17% | 2 609 | ~2 344 | 0.9× | ❌ pxpipe perdant |
| 8 369 chars | 17% | 2 733 | ~2 461 | 0.9× | ❌ pxpipe perdant |
| 12 389 chars | 26% | 3 560 | ~3 644 | 1.0× | ➖ neutre |
| 13 371 chars | 28% | 3 931 | ~3 933 | 1.0× | ➖ neutre |
| **48 000 chars** | **100%** | **~2 684** | **~14 118** | **5.3×** | ✅ théorique |

Aucun test réel n'a dépassé le seuil de rentabilité (historiques simulés trop courts).
Le ratio 5,8× initial (8K→406 tokens) était un artefact de mesure — le payload de 8K chars
contenait surtout du texte court avec beaucoup de structure Markdown, ce que pxpipe compresse bien.
En pratique, avec du texte dense, le ratio plafonne à ~5,3×.

## Assembleur fill_page.py

Script intelligent de construction de payload : `scripts/fill_page.py`

```python
from fill_page import assemble_payload
result = assemble_payload(
    base_template_path="templates/planner-payload.md",
    task="Question ou tâche à planifier...",
    history=[...],                # historique de conversation
    relevant_skills=[...],         # skills à charger en inline
    extra_context="..."            # contexte additionnel (DB state, etc.)
)
# result['system'] — payload système assemblé
# result['user_msg'] — message utilisateur
# result['total_chars'] — taille totale
# result['should_use_pxpipe'] — True si >9 100 chars
# result['pct_full'] — pourcentage de remplissage
```

Logique interne :
1. Charge le template de base (6 493 chars, descriptions outils/skills)
2. Ajoute l'historique (autant que la place disponible)
3. Ajoute les skills pertinents en descriptions compactes
4. Ajoute le contexte additionnel
5. Si place restante > seuil : ajoute tool schemas détaillés + padding skills
6. Retourne `should_use_pxpipe=False` si <9 100 chars → envoyer en texte direct

## Pitfalls

1. **Coût image FIXE = remplir ou ne pas utiliser.** ~2 684 tokens par page, qu'elle soit vide ou pleine. En dessous de 9 100 chars de payload, le texte direct est MOINS CHER que l'image. Ne pas utiliser pxpipe sous ce seuil. **Correction de Monsieur (2026-07-10).**

2. **Auth Kie.ai = Bearer, PAS x-api-key.** L'Anthropic SDK envoie `x-api-key` par défaut. Kie.ai le rejette (401). Toujours utiliser `Authorization: Bearer <key>`. pxpipe forwarde les headers du client — envoyer Bearer depuis le client.

3. **Cloudflare WAF : User-Agent obligatoire.** Sans `User-Agent: Mozilla/5.0...`, Kie.ai renvoie 403 Cloudflare. pxpipe forwarde le User-Agent du client.

4. **Ne pas utiliser le proxy Python.** Le proxy `/root/pxpipe-openrouter/` (1568×728) ne compresse quasiment rien (3 chars/token). Monsieur s'en est plaint.

5. **Pas de streaming via Kie.ai.** Cloudflare coupe les streams SSE. pxpipe est non-streaming par nature. Temps de réponse : 20-30s pour un planning, 40-60s pour un payload lourd.

6. **Fable 5 = pas de tool calling.** Confirmé sur la page modèle Kie.ai. Fable 5 est un Oracle/Planner uniquement. Déléguer l'exécution à GPT-5.5.

7. **Le cache Anthropic pour le multi-turn n'est PAS TESTÉ sur Kie.ai.** Toute l'architecture multi-turn (Planner→Executor en boucle) suppose que Kie.ai honore le cache prompt comme l'API Anthropic native. Si ce n'est pas le cas, l'économie pxpipe single-turn ne compense pas. **Risque #1 identifié par Fable 5 lui-même.**

8. **Safeguard Fable 5 : ne pas mettre le contexte dans `system`.** Fable 5 bloque les instructions système en image (anti-jailbreak). Injecter tout le contexte via le rôle `user`. Le champ `system` ne doit contenir qu'une instruction de formatage minimale.

9. **Validation : test méta.** Pour valider l'architecture, utiliser pxpipe sur la conversation même qui construit pxpipe. Fable 5 analyse son propre pipeline et identifie les angles morts. Pattern : payload brut (non résumé) + question stratégique.

## Dashboard

Accessible à `http://127.0.0.1:47821` — stats en direct, sessions, toggle compression, logs JSONL.

```bash
# Vérifier que pxpipe tourne
curl -s http://127.0.0.1:47821/ | head -5
# → <!doctype html>...pxpipe dashboard

# Voir les PNGs dumpés (debug)
ls /tmp/pxpipe_dump/
```
