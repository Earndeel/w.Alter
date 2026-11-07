---
name: osint-process-lessons
description: OSINT process improvement — lessons from identity resolution missions. Anti-patterns and best practices for social media research.
triggers:
  - OSINT identity research
  - social media profile discovery
  - person identification from partial data
---

# OSINT Process — Lessons Learned

## Golden Rule
**Nom + Activité + Lieu** — toujours dans cet ordre. Jamais de recherche par critères physiques (cheveux, âge, apparence). Les critères physiques servent uniquement au RECOUPEMENT VISUEL après avoir trouvé un candidat.

## Anti-patterns à éviter

### 1. Abandonner une piste sans preuve négative
Une piste n'est morte que quand on a une preuve formelle que ce n'est PAS la personne (localisation incompatible, âge incompatible, identité confirmée différente). "L'IA dit que c'est une photo stock" n'est PAS une preuve négative.

### 2. Faire confiance à la vision AI pour l'identification faciale
La vision AI se trompe sur :
- Les couleurs de cheveux (roux vs brun vs auburn)
- Photos réelles vs illustrations vs photos stock
- Comparaison entre deux visages
→ Utiliser l'IA pour extraire du TEXTE et des LABELS, pas pour identifier des personnes.

### 3. Screenshots répétitifs
1 screenshot + extraction structurée > 5 screenshots du même contenu. Si l'analyse ne trouve rien, SCROLL ou change de requête, ne re-screenshot pas.

### 4. Visiter des sites web morts
Vérifier le HTTP status (curl -sI) AVANT de prendre un screenshot ou d'analyser le contenu. Un 404 = passer au suivant.

### 5. Accepter un résultat sans vérification croisée
Un profil Facebook/Instagram n'est confirmé que quand la LOCALISATION et le CONTEXTE matchent. Vérifier la ville, le métier, les connections avant d'ajouter au dossier.

### 6. Utiliser Google Lens / reverse image pour les visages
Google Lens et la recherche inversée d'images ne fonctionnent PAS pour identifier des personnes (blocage 403, résultats hors-sujet). 
→ **Bon usage de l'image source** : la garder comme référence visuelle à l'écran, puis chercher des images via requête textuelle (Nom+Activité+Lieu), et comparer manuellement chaque résultat avec la référence.
→ L'image originale est un **étalon de comparaison**, jamais une requête.

## Best Practices

### 1. Analyse d'images : deux rôles distincts de la vision AI

**Rôle 1 — Extraction de contexte** (sur les images source) :
- Identifier les activités visibles (danse, sport, voyage)
- Repérer les lieux reconnaissables (monuments, paysages)
- Lire les objets/vêtements typiques (costume de danse, instrument)
- Extraire les textes/watermarks sur les images
→ Ce contexte devient un MOT-CLÉ PIVOT pour les recherches textuelles
→ Ex: Photo Tinder avec costume de danse → "danse orientale" → requête croisée avec nom+lieu

**Rôle 2 — Comparaison visuelle** (sur les résultats de recherche) :
- Prendre l'image source comme référence (description physique, traits distinctifs)
- Pour CHAQUE résultat image trouvé via requête textuelle, demander à la vision AI : "Est-ce que cette personne correspond à la description ?"
- La vision AI reconnaît les correspondances visuelles (même personne, même style, mêmes traits)
→ C'est comme ça qu'on trouve la cible dans les résultats — pas via Google Lens, mais via comparaison directe

**Anti-pattern :** Utiliser Google Lens / reverse image search pour les visages → ne marche pas (403, hors-sujet)
**Bon pattern :** Source comme étalon + requête textuelle + comparaison visuelle par la vision AI sur chaque résultat

### 2. Connexions transversales immédiates
Dès qu'un NOM, HANDLE ou MARQUE est trouvé sur une plateforme → le chercher immédiatement sur toutes les autres :
- Google (web + images)
- Instagram, Facebook, LinkedIn, TikTok
- StarNgage, SocialBlade (analytics influenceurs)
- Codeur.com, Malt.fr, ComeUp.com (freelances FR)
- Wayback Machine (sites morts)

### 3. Handle → écosystème
Un handle Instagram trouvé = chercher :
- site:instagram.com "handle" sur Google
- "handle" sur StarNgage/SocialBlade pour analytics
- "handle" + nom sur Google pour cross-references
- Posts tagués par d'autres comptes

### 4. Toujours scroller les résultats images
Les images pertinentes sont souvent au-delà de la première grille. Scroller 2-3 pages minimum.

### 5. Google Images via Scrapling quand Camoufox est bloqué
Si Google CAPTCHA dans le navigateur → utiliser mcp_scrapling_stealthy_fetch avec solve_cloudflare=True pour contourner.

### 6. Kardex : ne jamais ajouter sans vérification
Chaque entrée dans le kardex doit avoir :
- Source identifiée
- Score de confiance
- Preuve de localisation/contexte
- Pas de doublons ou contradictions

## Pipeline OSINT optimal

```
1. Analyse des images source (Tinder, WhatsApp, etc.)
   → Extraire ACTIVITÉS, LIEUX, CONTEXTE (pas les visages)
   → Ex: costume de danse → "danse orientale"

2. Recherche textuelle : Nom + Activité + Lieu
   → Google Images, Bing Images (pas de reverse image search)

3. Résultat trouvé → Extraire handle/nom/site
   → Chercher sur TOUTES les plateformes immédiatement

4. Profil trouvé → Extraire bio complète, posts, connexions
   → Chercher les mentions/tags par d'autres comptes

5. Cross-reference → StarNgage, analytics, Wayback
   → Vérifier cohérence (ville, métier, âge)

6. Recoupement visuel → Comparer image source avec résultats
   → Garder l'image originale comme étalon, comparer visuellement

7. Kardex → Structurer les données
   → Ne jamais ajouter sans preuve
```
   → L'image source = étalon de comparaison, PAS requête de recherche inversée
```
6. Kardex → Structurer les données
   → Ne jamais ajouter sans preuve
```
