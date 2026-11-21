---
name: enrichir-composition-produit
description: Use when a product comparison needs composition facts (sugar, caffeine, ingredients) and only when they change the ranking.
---

# Enrichir la composition d'un produit

1. Ne lancer que si un critère de Monsieur porte sur la composition (sucre, caféine, lait, qualité des ingrédients).
2. Sources dans l'ordre : fiche officielle du fabricant/enseigne > étiquette photographiée > base nutritionnelle publique.
3. Rendre des observations (`values.sugar_g`, `values.caffeine_mg`, `values.ingredients`) avec la portion exacte
   (par gobelet, par 100 ml) ; ne jamais convertir sans la portion.
4. Une composition vaut 30 jours (réutilisable) ; un prix vaut 24 h.

## Ce qui a marché
- (à compléter au premier usage)

## Ce qui a échoué
- (à compléter)
