# Kie.ai — Grok Imagine Video 1.5 Preview (contrat live)

Référence vérifiée sur la page Market Kie.ai le 25 juillet 2026. Cette fiche prévaut sur les anciennes recettes génériques lorsqu’un utilisateur demande explicitement **Grok Imagine Video 1.5**.

## Modèle et distinction importante

- Modèle actuel : `grok-imagine-video-1-5-preview`
- Endpoint : `POST https://api.kie.ai/api/v1/jobs/createTask`
- Ne pas remplacer silencieusement ce modèle par `grok-imagine/text-to-video` : ce dernier est une autre route Grok générique/ancienne.
- Le modèle 1.5 Preview génère une piste audio native synchronisée. Aucun champ `generate_audio` n’était exposé par le formulaire Market vérifié.

## Payload T2V vérifié

```json
{
  "model": "grok-imagine-video-1-5-preview",
  "input": {
    "prompt": "A single flowing visual description... Include exact spoken dialogue when native audio is desired.",
    "aspect_ratio": "9:16",
    "resolution": "720p",
    "duration": 15,
    "nsfw_checker": true
  }
}
```

Paramètres vus sur la page live :

- `aspect_ratio` : `auto`, `1:1`, `16:9`, `9:16`, `3:2`, `2:3`
- `resolution` : `480p` ou `720p`
- `duration` : entier de 1 à 15 secondes, défaut 8
- `nsfw_checker` : booléen, activé par défaut dans le Playground
- `image_urls` : optionnel si une référence visuelle est fournie

Ne pas envoyer `aspect`, `aspectRatio`, `seconds` ou `mode` sans avoir vérifié que la route ciblée les accepte : ces noms proviennent de recettes d’autres familles ou d’anciennes versions.

## Prompting

Le prompt doit décrire ce que le spectateur voit, dans un seul flux narratif :

1. pas de storyboard numéroté pour une scène UGC simple ;
2. pas de jargon de tournage (`tracking shot`, `35mm`, `dolly`, etc.) ;
3. décrire les matières, la lumière, les gestes, l’environnement et les actions physiques ;
4. inclure le dialogue français exact dans le prompt si l’audio natif est voulu ;
5. demander explicitement l’absence de sous-titres, logos, filigranes et texte lisible lorsque l’habillage sera ajouté en postproduction ;
6. réserver visuellement une zone propre pour les overlays ;
7. si l’identité exacte d’un produit compte, préférer I2V avec une vraie image de référence : le T2V invente facilement une installation générique.

## Soumission, polling et téléchargement

La création réussie renvoie généralement `data.taskId` et `data.recordId`.

```text
GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<taskId>
```

États à gérer : `waiting`, puis `success` ou `failed`. Poller à intervalles espacés (environ 60 secondes) et arrêter dès le terminal state. À `success`, chercher d’abord `data.resultJson.resultUrls[0]`, puis les variantes `result_url`/`resultUrl` si la réponse diffère.

Télécharger immédiatement l’URL retournée : les URLs temporaires de génération ne sont pas des artefacts permanents.

## Contrôle obligatoire après rendu

Ne pas annoncer la réussite sur le seul `HTTP 200` de création.

```bash
ffprobe -v error \
  -show_entries format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,sample_rate,channels \
  -of json output.mp4

ffmpeg -hide_banner -i output.mp4 -af volumedetect -f null - 2>&1
```

Vérifier : durée proche de la demande, ratio/résolution, 24 fps si fourni ainsi par le modèle, présence d’une piste audio et niveau non silencieux. Extraire ensuite quelques frames de début/milieu/fin pour contrôler : texte ou logo halluciné, cohérence du produit, visage/mains, composition et espace réservé aux sous-titres.

## Coût

La page Market indiquait environ 1,6 crédit/s en 480p et 3 crédits/s en 720p. Le coût effectif est la source de vérité : lire le solde avant la tâche, lire le solde après, puis calculer la différence. À titre de contrôle, une tâche de 15 s en 720p a consommé 45 crédits lors de la vérification live du 25 juillet 2026.
