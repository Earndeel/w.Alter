---
name: osint-public-profile-lookup
description: Use for OSINT lookup of social profiles without login.
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [osint, research, social-media, kardex]
---

# OSINT public de profils sociaux — routes vérifiées

Complément à la skill `beeper-messages` (référence contact-profile-analysis) pour la partie recherche web publique. Vérifié en opération le 2026-08-22 (cible: hamoni14).

## When to Use

Recherche OSINT d'un contact à partir d'un handle ou d'indices de conversation Beeper, quand aucune session navigateur authentifiée n'est disponible.

## Routes qui marchent depuis un VPS (sans login)

1. **Google via SerpApi MCP** (`mcp__serpapi__search`, engine=google_light) : indexe les profils IG **privés** avec stats dans le snippet ("383 followers. This profile is private."). C'est souvent la SEULE source donnant followers/following d'un compte privé.
2. **google_images** : remonte les posts publics qui taggent le handle (`lookaside.instagram.com/seo/google_widget/crawler/?media_id=...`) + noms des taggueurs → graphe social gratuit.
3. **TikTok embed** : `curl https://www.tiktok.com/embed/@handle` avec UA desktop renvoie un JSON embarqué complet SANS challenge : userId, nickname, followerCount, videoCount, heartCount, avatarThumbUrl. Distingue compte actif vs coquille (0 video/0 follower).
4. **ID numérique Instagram** : présent dans les métadonnées Beeper (`participants.items[].id` = `@instagramgo_<ID>:beeper.local`). Zéro scraping nécessaire.
5. **Photo de profil Beeper** : `imgURL` = chemin local Mac → SCP via tailnet direct (`ssh -o BatchMode=yes lucasjouvencon@100.x.y.z`). Le tunnel localhost:2222 du ~/.ssh/config est souvent mort ; tester le tailnet d'abord.

## Pièges confirmés

- **Brave API** : clé vault peut renvoyer 422 SUBSCRIPTION_TOKEN_INVALID → basculer sur SerpApi, ne pas s'acharner.
- **IG web_profile_info** depuis datacenter : rate-limit quasi systématique ("Please wait a few minutes").
- **Miroirs IG** (imginn/picuki/gramhir) : 403 ou Cloudflare depuis datacenter.
- **tikwm.com** : Cloudflare challenge.
- **Threads** `/embed` avec UA Googlebot : page servie mais données user absentes si profil inexistant/inactif — test d'existence indirect seulement.
- **Bing/DDG** : n'indexent pas les handles de petits comptes → résultats bruités (faux positifs chinois/YouTube).
- **X / Facebook public search** : 404/vide pour handles personnels low-profile.

## Persistance Kardex (schéma kardex de hindsight-pg)

- Contact : `INSERT INTO kardex.contacts (...)` — handles en jsonb (instagram, instagram_id, tiktok, beeper_chat), key_facts en array, sources datées ("osint_web_YYYY-MM-DD").
- Événements : `kardex.relationship_events (contact_id, event_type, title, description, date_start, importance, status='confirmed', confidence)` — PAS de colonne event_date/source.
- Boucles : `kardex.open_loops (contact_id, loop_type, description, opened_at, priority, status='open', confidence)` — PAS de colonne loop_name.
- Cluster : `kardex.identity_clusters (canonical_contact_id, status, cluster_label, confidence, evidence_summary, metadata jsonb)`.
- Attention : toute erreur SQL fait rollback du batch → réinsérer tout après correction.
- Photo : copier sous `/root/Downloads/kardex_media/<handle>/profile_avatar.jpg`, référencer dans `contacts.photo_url`.

## Verdict type "empreinte faible"

Si Google trouve le profil mais ni Bing/DDG/X/FB/TikTok actif : empreinte délibérément minimale, concentrée sur IG privé. Le rapport doit le dire tel quel (le silence EST l'information) et lister les gaps (nom réel, profession, ville d'origine) en open_loops info_gap.
