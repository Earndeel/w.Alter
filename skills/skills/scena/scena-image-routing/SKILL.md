---
name: scena-image-routing
description: "Image generation routing logic: Atlas Cloud (ERNIE/GPT-Image) vs Kie.ai vs Z-Image vs PiAPI — when to use each, pricing, and fallback chain."
version: 1.0.0
author: Lucas + W.Alter
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [scena, image, routing, atlas-cloud, kie, provider]
---

# Image Routing — Scena

## When to Use

- Scena or any workflow needs to generate an image and must pick the right provider
- Choosing between Atlas Cloud, Kie.ai, Z-Image, or PiAPI for image generation
- Need fallback chain logic when a provider returns 402 or is unavailable
- Configuring image generation routing for a new tenant or pipeline

## Provider Decision Matrix

| Use Case | Provider | Model | Why |
|----------|----------|-------|-----|
| Génération rapide texte→image | **Atlas Cloud** | ERNIE-Image-Turbo | ~2-3s, $0.01/image, bonne qualité |
| Qualité premium texte→image | **Kie.ai** | grok-imagine/image-to-video | Haute fidélité, mais ~30s |
| GPT-Image 2 T2I | **Atlas Cloud** | gpt-image-2/text-to-image | Bypass direct Atlas, pas besoin d'OpenAI key |
| GPT-Image 2 I2I | **Kie.ai** | grok-imagine/image-to-image | Meilleure référence preservation |
| Vidéo I2V | **Kie.ai** | Seedance 2.0, Kling v2 | Multi-modèles vidéo |
| Fallback gratuit | **Atlas Cloud** | ERNIE-Image-Turbo | Toujours dispo, cheapest |

## Credentials Vault Paths

- Atlas Cloud : `vault get atlas/api_key`
- Kie.ai : `vault get kie/api_key`

## Pitfalls

- **Kie.ai 402** quand le compte n'a plus de funds — fallback immédiat sur Atlas Cloud
- **Atlas Cloud async** : submit → poll `prediction/{id}` — pattern différent de Kie.ai
- **Z-Image** : modèle chinois de Kie.ai, qualité correcte mais pas pour les faces humaines
- **GPT-Image 2 sur Atlas** : les paramètres `size`, `quality` mappent différemment — `size=hd` = 1440x2560, `size=low` = résolution réduite
- **Ne JAMAIS** hardcoder les clés API — toujours vault first
