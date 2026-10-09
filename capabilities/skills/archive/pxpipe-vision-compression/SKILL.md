---
name: pxpipe-vision-compression
description: Compression de contexte via canal vision — pxpipe (teamchong/pxpipe) encode le system prompt + tool docs + historique en PNG 1568×1568 pour modèles vision (Fable 5, Claude). Exploite la densité supérieure du canal vision (~3,1 chars/image-token vs ~1 char/texte-token). Économie réelle 7× sur sessions longues (pas via cache Anthropic — via densité par token). Use when planning heavy-context tasks for Fable 5 or evaluating whether to use pxpipe for a given workload.
---

# pxpipe Vision Compression

## Principe

Le canal vision de Fable 5/Claude encode ~3,1 caractères par token image
contre ~1 caractère par token texte. pxpipe render le contexte en PNG
monospace à très haute densité, remplaçant le texte par des images.

Ce n'est PAS une optimisation de cache Anthropic — c'est un pur gain de densité.

## Specs réelles (teamchong/pxpipe)

| Paramètre | Valeur |
|---|---|
| Taille image | 1568×1568 px |
| Tokens par image | 2 684 |
| Chars par image | ~48 000 |
| Ratio densité | 3,1 chars/image-token |
| Contexte Fable 5 | 1 000 000 tokens |

## Capacité max Fable 5

```
992 000 tokens dispo (1M − 8K réponse)
÷ 2 684 tokens/image
= 369 images max
× 48 000 chars/image
= ~17,7 MILLIONS de caractères
```

## Économie mesurée (README pxpipe)

| | Avec pxpipe | Sans pxpipe |
|---|---|---|
| Coût session | $6,06 | $42,21 |
| Contexte utilisé | 73 500/1M | 96% plein |
| Ratio | **7× moins cher** | — |

## Quand utiliser pxpipe

- **Session single-turn lourde** : briefing massif, planification complexe
- **Contexte >50K tokens** : le gain de densité dépasse le coût de rendu
- **Tâche créative** : vidéo, design, storytelling — Fable 5 excelle
- **Qualité > coût** : Fable 5 planifie mieux que DeepSeek

## Quand NE PAS utiliser pxpipe

- **Session multi-turn** : le texte + cache Anthropic est imbattable (cache hit = 90% réduction)
- **Tâche simple** : overhead pxpipe > gain
- **Modèle non-vision** : pxpipe ne sert à rien sur du texte pur

## Vrai pxpipe opérationnel (teamchong) ✅

Le vrai pxpipe est installé et fonctionnel à `/root/pxpipe/`. Mesure réelle : **5,8× compression**
(8 024 chars system → 406 tokens, vs ~2 360 en texte).

**Lancement (Kie.ai upstream) :**
```bash
cd /root/pxpipe
ANTHROPIC_UPSTREAM=https://api.kie.ai/claude \
  PXPIPE_MODELS="claude-fable-5,claude-opus-4-8" \
  npx tsx src/node.ts
```

**Auth Kie.ai :** `Authorization: Bearer <key>` (PAS `x-api-key`) + `User-Agent: Mozilla/5.0...`.
Dashboard : `http://127.0.0.1:47821`.

## Notre proxy custom (pxpipe-openrouter) — OBSOLÈTE

⚠️ `/root/pxpipe-openrouter/proxy.py` (1568×728, ~6 240 chars/image, ~3 chars/token)
est DÉCONSEILLÉ. Gain quasi nul. Remplacé par le vrai pxpipe.

## Références

- Repo officiel : `https://github.com/teamchong/pxpipe`
- Doc technique : `https://raw.githubusercontent.com/teamchong/pxpipe/main/docs/TRANSFORM_INFO.md`
- `references/pxpipe-real-specs.md` — comparaison détaillée proxy vs vrai pxpipe
