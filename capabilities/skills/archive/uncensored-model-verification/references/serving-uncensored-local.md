# Serving un modèle uncensored/ablité en local — vast.ai MoE GGUF

Pattern pour un MoE 100B+ (classe GLM-5.3-Flash) quand aucun SaaS ne passe le test de sonde.

## Dimensionner avant de choisir l'offre

Sommer les tailles `*.gguf` par quantisation via l'API HF :

```
GET https://huggingface.co/api/models/<repo>?blobs=true
```

Pondérer `size` des fichiers `.gguf` groupés par le token de quant dans le nom. Ordres de grandeur mesurés pour un MoE ~170B :

| Quant | Taille |
|---|---|
| Q3_K_M | ~153 Go |
| Q4_K_M | ~193 Go |
| Q8_0 | ~341 Go |

## Offre et runtime

- 2×RTX 4090 (~0,64-0,87 $/h) + llama.cpp avec `--n-cpu-moe` : les experts résident en RAM hôte (256 Go+ sur les box standard), les GPU gardent attention/KV → 15-30 tok/s en chat.
- Alternative plus simple mais plus chère : 1×A100 80 Go (~1,00 $/h) — offload moindre, setup plus court.
- Disk ≥ taille du modèle + 20% (un Q4_K_M de 193 Go ne rentre pas dans un disk 100).
- Pré-télécharger le GGUF dans un template (snapshot ou onstart) : un téléchargement de 150-200 Go coûte ~30 min à chaque spin-up sinon.

## Coût réel

Session à la demande + destruction systématique = ~1 $ par soirée d'usage. Stockage d'une instance stoppée ≈ 0,05 $/h/100 Go — si l'usage devient quotidien, préférer un modèle plus petit ablité en local (0 $/h).