---
name: comparer-offres-produits
description: Use when comparable offers must be collected from several shops in parallel, one routed sub-agent per shop, as sourced observations of the run.
---

# Comparer des offres produits

1. Un `walter_run` par enseigne/source, lancés en parallèle (indépendants) :
   `task="research"`, `level="L2"`, `constraints={"geo": {...}}`, `persist="observations"`,
   `output_schema={"observations": [{"subject": "str", "seller": "str", "source_url": "str", "values": {"price": "number|null", "currency": "str", "volume": "str|null"}, "method": "str", "confidence": "high|medium|low"}]}`.
2. Goal du sous-agent : l'enseigne, la catégorie, les tailles/variantes à couvrir, « une observation par taille »,
   « sélectionne explicitement la zone ou le magasin sur le site », « inconnu plutôt qu'une estimation ».
3. Vérifier le retour : `persisted.stored` ; les erreurs listent les observations rejetées (source manquante…).
4. Ne pas relancer une enseigne dont les observations de moins de 24 h existent (`walter-memory observations recent`).

## Ce qui a marché
- 27/10 : un sous-agent routé (gpt-6.1-sol) avec walter_browse a rendu 2 offres sourcées en 59 s.

## Ce qui a échoué
- Sans contrat de sortie, les réponses ne sont pas stockables (pas de liste `observations`).
