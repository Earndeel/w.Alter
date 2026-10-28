---
name: decouverte-commerces-proches
description: Use when a local shopping research needs the shops and sources that serve a zone (chains, apps, official menus) before comparing offers.
---

# Découverte des commerces proches

1. Partir de la zone donnée par Monsieur (quartier, ville, pays). Ne pas inventer de position.
2. Lister les enseignes probables pour la catégorie (supérettes, chaînes de café, livraison) avec `walter_browse(query=…)`
   en langue locale et en anglais ; garder pour chacune l'URL officielle (menu, catalogue, appli) et son type d'accès.
3. Classer les sources : site officiel avec prix > appli de livraison > article/blog daté > extrait de recherche.
4. Sortie : `[{seller, source_url, access: "public|login|app", note}]`, sans prix (la comparaison vient après).

## Ce qui a marché
- Thaïlande : 7-Eleven (All Café) publie ses boissons sur 7eleven.co.th/new-product/drink/… avec prix par taille.

## Ce qui a échoué
- Requêtes trop longues ou entre guillemets : 0 résultat (DDG) ; préférer 4-6 mots.
