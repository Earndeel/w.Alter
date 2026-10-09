# pxpipe réel (teamchong) vs notre proxy pxpipe-openrouter

## Spécifications comparées

| | Notre proxy | Vrai pxpipe |
|---|---|---|
| Repo | `/root/pxpipe-openrouter/` | `github.com/teamchong/pxpipe` |
| Langage | Python | TypeScript (Node.js) |
| Taille image | 1568×728 | **1568×1568** |
| Tokens par image | ~2 000 | **2 684** |
| Chars par image | ~6 240 | **~48 000** |
| Ratio densité | ~3 chars/token | **~3,1 chars/image-token** |
| Protocole | Proxy HTTP Anthropic→OpenRouter | Proxy HTTP Anthropic→Anthropic |

## Pourquoi le vrai pxpipe est 7,7× plus dense

La différence vient de la hauteur d'image : 728 vs 1568 pixels.

Notre proxy a été écrit en Python pour s'interfacer avec OpenRouter
(pas d'accès direct à l'API Anthropic). Le vrai pxpipe est en TypeScript
et interface directement avec l'API Anthropic.

## Capacité max Fable 5 (vrai pxpipe)

```
Contexte Fable 5       1 000 000 tokens
Réserve réponse           −8 000 tokens
Disponible                992 000 tokens
÷ 2 684 tokens/image    = 369 images
× 48 000 chars/image    = 17 736 000 caractères
```

## Session réelle documentée (README pxpipe)

```
Coût avec pxpipe :    $6,06
Contexte utilisé :    73 500 / 1 000 000 tokens
Coût sans pxpipe :    $42,21 (contexte à 96%)
Économie :            7×
```

## Points clés

1. pxpipe n'économise PAS via le cache Anthropic — il exploite la densité vision
2. Le cache Anthropic (texte) reste meilleur pour le multi-turn
3. pxpipe brille en single-turn où le cache ne peut pas aider
4. Notre proxy est une version dégradée — à remplacer par le vrai pxpipe si possible
