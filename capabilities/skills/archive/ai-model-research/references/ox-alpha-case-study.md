# Cas d'étude — Ox Alpha (stealth/ox-alpha), août 2026

Session réelle du 2026-08-21. Sert de méthode-type pour « c'est quoi ce modèle stealth ».

## Fiche vérifiée (source : GET /api/v1/models, filtré sur id)

| Champ | Valeur |
|---|---|
| Créé | 2026-08-20 |
| Contexte | 1 048 576 tokens · sortie max 131 072 |
| Modalités (claim) | text+image+video → text — 1re release anonyme à annoncer la vidéo |
| Reasoning | obligatoire, effort défaut "max", efforts max/high/low |
| Pricing | $0/$0 pendant ~1 semaine, prix final inconnu |
| Perf dashboard OR | ~50 tok/s · ~2 s P50 · uptime 99,99 % · tool-call err ~4,45 % |
| Traffic early | Claude Code ~9,3 Md tokens · Hermes Agent ~9 Md · Zed |

Fine print : prompts/completions retenus par le provider, « not used for training » ;
le claim marketing « zero data retention » est plus fort que les termes réels.

## Playbook stealth (historique complet au moment du cas)

Anonymat → burst de traffic gratuit → reveal par un labo chinois :
Pony Alpha (fév) → Zhipu GLM-5 · Hunter+Healer Alpha (mars) → Xiaomi MiMo-V2-Pro/Omni
(1 000 Md de tokens avalés pendant la fenêtre anonyme) · Elephant Alpha (avr) → Ant Group
Lingxi · Owl Alpha (avr) → Meituan LongCat-2.0 · Ox Alpha (20 août) → non revendiqué au 21/08.
Lecture standard : l'anonymat supprime le biais de marque et crowdsourcce l'évaluation ;
le claim « 100T tokens/jour » ressemble à un stress-test d'infra déguisé en promo.

## Sentiment communautaire (au 21/08)

Accès : Reddit direct bloqué → Arctic Shift par link_id ; X indisponible (crédits xAI) → cité via Reddit.

**Camp MiMo V3** (r/opencode, thread 1vtw0aq, ~70 commentaires — utilisateurs pratiques) :
- « Very likely MiMo V3 » parmi les top comments ; précédent Hunter Alpha → V2-Pro.
- Signal modalités : MiMo v2.5 = image+audio ; Ox Alpha perd l'audio, gagne la vidéo → cohérent V3.
- Xiaomi a l'habitude des programmes « 100T tokens ». Contre-point : EQ-Bench 2.1 ≈ 84 vs ~78 MiMo 2.5.

**Camp GLM 5.3/5.5** (r/LocalLLaMA, thread 1vu620d — testeurs comportementaux) :
- Test de chevauchement de formulations : « basically an improved GLM 5.3 » ; contexte 1M collerait mieux à Zhipu.
- Sur X (relais Reddit) : « people on x say its glm 5.3 ». Variantes GLM 5.5, GLM-5.3V.

**Minoritaires** : MiniMax M3 Pro · LongCat 2.5/3.0 (théorie alphabétique Owl→Ox) · hy4.

**Consensus transversal** :
- Origine chinoise quasi certaine (refus Taïwan/Tiananmen constatés, coupures mid-stream).
- Vision réellement fonctionnelle (test screenshot Arashiyama confirmé).
- Coding solide (« night and day » vs Muse Spark 1.2, plan avec ¼ des tokens).
- Cutoff ≈ décembre 2025.
- ZDR perçu comme sus (top comment, s=12) : stress-test ou feedback, pas data-flywheel.

## Leçon méthodo

Les camps suivent la méthode de leurs auteurs : similarité de style (copiable, faible)
vs signaux d'architecture (modalités, censure, cache — plus fiables). Aucun verdict avant
le reveal officiel ; le mystère fait partie du marketing.

## Sources

- openrouter.ai/provider/stealth · api/v1/models (primaire)
- orcarouter.ai/blog/ox-alpha-stealth-model-what-we-know (historique playbook)
- explainx.ai/blog/openrouter-ox-alpha-stealth-model-august-2026 (specs dashboard)
- Reddit 1vu620d (r/LocalLLaMA) + 1vtw0aq (r/opencode) via Arctic Shift
