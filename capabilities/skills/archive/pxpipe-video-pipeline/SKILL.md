---
name: pxpipe-video-pipeline
description: Pipeline vidéo économique — pxpipe (briefing PNG → Fable 5 planification) → génération image → Kie.ai image-to-video. Workflow complet validé pour Grok Imagine Video 1.5.
---

# pxpipe Video Pipeline

Pipeline économique pour la génération vidéo Kie.ai avec planification par Fable 5.

## Prérequis

- pxpipe-openrouter installé dans `/root/pxpipe-openrouter/`
- Clé OpenRouter dans `/root/.hermes/.env` (`OPENROUTER_API_KEY=sk-or-v1-...`)
- Clé Kie.ai (`KIE_API_KEY`)

## PITFALL: La clé OpenRouter doit être sourcée

Le proxy pxpipe ne détecte PAS automatiquement la clé. Avant de démarrer :

```bash
export $(grep -v '^#' /root/.hermes/.env | xargs)
```

Sans cela → HTTP 401 d'OpenRouter.

## Workflow complet

```
1. Briefing → /tmp/video_brief.txt (description textuelle de la scène)
2. Source .env (OPENROUTER_API_KEY)
3. Démarrer proxy: cd /root/pxpipe-openrouter && python3 proxy.py --port 47821 --verbose &
4. Envoyer le brief au proxy en Anthropic-format:
   - model: anthropic/claude-fable-5
   - system: contenu du brief (rendu en PNG par pxpipe)
   - user: "Plan this. Return ONLY valid JSON: {keyframe_prompt, motion_prompt}"
5. Fable 5 répond en ~15s avec les prompts optimisés
6. Générer image keyframe avec le keyframe_prompt (GPT Image-2)
7. Upload image → catbox.moe (curl -sF "reqtype=fileupload" -F "fileToUpload=@img.png" https://catbox.moe/user/api.php)
8. Envoyer à Kie.ai: POST /api/v1/jobs/createTask avec image_urls + motion_prompt
9. Poll /api/v1/jobs/recordInfo?taskId=... jusqu'à success
```

## Tableau des coûts

| Étape | Modèle | Coût |
|-------|--------|------|
| Planification | Fable 5 (pxpipe) | ~$0.02-0.05 |
| Keyframe | GPT Image-2 Medium | 1 image |
| Vidéo | Grok Imagine 1.5 (Kie) | 30 crédits ($0.15) |
| **Total** | | **~$0.20** |

## Note sur les crédits Kie.ai

Les deux modes (text-to-video et image-to-video) coûtent le même prix : 30 crédits pour 10s 720p. L'image-to-video offre un meilleur contrôle artistique, pas une réduction de coût.
