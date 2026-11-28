# Grok Imagine Video 1.5 — Kie.ai

## Models

| Model ID | Mode | Credits (10s/720p) |
|---|---|---|
| `grok-imagine/text-to-video` | Texte → vidéo | 30 |
| `grok-imagine/image-to-video` | Image + motion prompt → vidéo | 30 |

**Note :** Les deux modes coûtent le même prix (30 crédits). L'image-to-video n'offre pas
d'économie de crédits, seulement un meilleur contrôle de la frame de départ.

## Image-to-video payload

```json
{
    "model": "grok-imagine/image-to-video",
    "input": {
        "image_urls": ["https://files.catbox.moe/xxxxx.png"],
        "prompt": "Motion description (2-3 phrases max, décrit l'action à partir du keyframe)",
        "mode": "normal",
        "duration": "10",
        "resolution": "720p",
        "aspect_ratio": "16:9"
    }
}
```

## Text-to-video payload

```json
{
    "model": "grok-imagine/text-to-video",
    "input": {
        "prompt": "Description complète de la scène...",
        "mode": "normal",
        "duration": "10",
        "resolution": "720p",
        "aspect_ratio": "16:9"
    }
}
```

## Endpoints

| Action | Méthode | URL |
|---|---|---|
| Créer tâche | POST | `https://api.kie.ai/api/v1/jobs/createTask` |
| Polling statut | GET | `https://api.kie.ai/api/v1/jobs/recordInfo?taskId={taskId}` |

## Polling

Le polling retourne un objet avec `state` : `waiting` → `success` → `failed`.
En cas de succès, `result_url` contient l'URL de la vidéo.

État `waiting` : la tâche est en file d'attente. Relancer le polling après 60-90s.
Pas de délai fixe — le rendu prend typiquement 60-120 secondes.

## Upload d'image pour image-to-video

Utiliser catbox.moe (gratuit, pas d'auth) :

```bash
curl -sF "reqtype=fileupload" \
  -F "fileToUpload=@/path/to/keyframe.png" \
  https://catbox.moe/user/api.php
```

Retourne une URL directe utilisable dans `image_urls`.
