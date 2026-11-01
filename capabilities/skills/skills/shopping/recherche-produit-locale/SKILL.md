---
name: recherche-produit-locale
description: Use when Monsieur asks for the best product or offer near him (prices, volumes, composition, Pareto) — local shopping research across shops with sourced offers.
---

# Recherche de produit locale (skill d'entrée)

Coordonne une recherche d'offres locales comparables (café glacé, boisson, produit de supérette…). Ce skill ne
réimplémente rien : le web passe par walter-browse (via `walter_run`), les offres sont stockées par Walter Memory
(observations sourcées), le calcul est déterministe (`scripts/pareto.py`).

## Procédures (lire seulement celles utiles)
1. `decouverte-commerces-proches` — quelles enseignes et sources pour la zone.
2. `comparer-offres-produits` — lancer les sous-agents, une enseigne/source par sous-agent.
3. `enrichir-composition-produit` — sucre, caféine, ingrédients, seulement si cela change la comparaison.
4. `valider-offres-sourcees` — recouper, niveaux de preuve, contradictions.

## Déroulé
1. **Zone** : prendre la zone que Monsieur donne dans sa demande (quartier, ville). Si elle manque ou date d'avant
   aujourd'hui, la demander. Ne jamais déduire la zone d'une ancienne position. Une position GPS est local_only : ne
   jamais la mettre dans un prompt.
2. **Critères** : noter les critères de Monsieur (prix, prix/100 ml, volume, sucre, qualité…), leur sens (min/max)
   et ce qui est une contrainte dure.
3. **Réutiliser** : `walter-memory observations recent "<produit> <enseigne>" --max-age-hours 24` ; une offre fraîche
   et sourcée évite une relecture.
4. **Déléguer en parallèle** : un `walter_run` par enseigne/source (procédure 2) avec
   `task="research"`, `level="L2"`, `constraints={"geo": {"zone": …, "pays": …, "devise": …, "langue": …}}`,
   `output_schema={"observations": [Observation v1]}`, `persist="observations"`.
5. **Pareto** : `walter-memory observations run <run_id> | python3 scripts/pareto.py --min price --min price_per_100ml --max volume_ml`
   (ajouter `--min sugar_g` etc. selon les critères ; `--weights` seulement pour un classement secondaire).
6. **Répondre** : frontière de Pareto d'abord, puis compromis, offres non comparables (données manquantes) à part,
   sources et dates, limites (zone vérifiée ou non, sortie réseau, prix indicatif vs confirmé).

## Observation v1 (contrat de sortie des sous-agents)
`{"subject", "seller", "source_url", "values": {"price", "currency", "volume", "sugar_g", "caffeine_mg"}, "source_date",
"method": "search_snippet|http|static_html|browser|api", "confidence": "high|medium|low"}` — `null` ou « inconnu »
pour une valeur absente ; jamais d'estimation.

## Réseau
Les lectures de page partent par l'IP réelle de Monsieur (Mac hors « Lucas ») et sont refusées sinon : un sous-agent
peut alors rendre des offres issues des seuls extraits de recherche (`method: search_snippet`, confiance basse). Le
dire dans la réponse.

## Ce qui a marché
- 27/10 : 7eleven.co.th/new-product/drink/… donne prix et volumes au menu froid (americano 16 oz 35 THB, 22 oz 45 THB).
- Les recherches en thaï (« อเมริกาโน่เย็น ราคา ») trouvent les pages officielles mieux qu'en anglais.

## Ce qui a échoué
- 27/10 : un sous-agent avec un terminal a interrogé Google/Bing directement depuis le serveur : interdit, utiliser walter_browse.
- 28/10 : Mac sur « Lucas » → lectures de page refusées → prix « inconnu » (comportement voulu, pas une panne).
