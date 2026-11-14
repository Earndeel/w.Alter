# Référence — batterie de métriques de communication du Kardex

Script : `scripts/kardex_comm_metrics.py` · Stockage : `kardex.communication_patterns` (contact_id, pattern_type, pattern, metric_value JSONB).

## Usage

```bash
/root/.hermes/hermes-agent/venv/bin/python /root/.hermes/skills/research/osint-public-profile-lookup/scripts/kardex_comm_metrics.py all   # tous les contacts
/root/.hermes/hermes-agent/venv/bin/python .../kardex_comm_metrics.py 10 1   # contacts spécifiques
```

Pré-requis : les messages doivent être dans `kardex.messages` (sender='lucus'|'contact', text, timestamp UTC, has_attachments). Le script est **idempotent** : il purge ses propres pattern_types avant réinsertion.

## Les 15 patterns générés

**Dynamique conversationnelle (5)**
- `comm_volume_direction` — total, ratio contact/lucas
- `comm_latency` — latence médiane chaque côté, % <2min
- `comm_initiative` — qui reprend après gap >3h
- `comm_turn_taking` — messages consécutifs avant de laisser la parole
- `comm_media_ratio` — part des médias envoyés par le contact

**Style linguistique (8)**
- `length_profile` — longueur médiane/max, % multi-lignes
- `syntax_sentence_structure` — phrases/msg, mots/phrase (méd + p90)
- `syntax_openers` — débuts I/Haha/You/other
- `syntax_contractions` — taux de contraction, apostrophes omises
- `non_native_markers` — espaces avant ponctuation, calques
- `system_emoji_inventory` — top10, placement (end/mid/start), densité
- `system_punctuation` — !!, ?, ..., !
- `system_laughter` — % messages rieurs, variantes (haha vs lol vs 😂)

**Autres (2)**
- `lexicon_top_words` — top20 vocabulaire
- `evolution_daily_metrics` — par jour BKK : n, len_med, emoji/msg, haha%

## Ingestion Beeper → kardex.messages

Pattern d'insertion idempotent (voir session 2026-08-22) :
```sql
INSERT INTO kardex.messages (contact_id, channel_id, source, sender, text, timestamp, has_attachments, attachment_types, source_message_id)
SELECT ... WHERE NOT EXISTS (SELECT 1 FROM kardex.messages WHERE source_message_id=%s)
```
sender = 'lucas' si isSender sinon 'contact'. TEXT→text ; IMAGE/VIDEO/STICKER→has_attachments=true.

## Limites connues

- Fuseau évolution codé en dur UTC+7 (Bangkok).
- Détection non-natif heuristique (espaces avant !, calques) — sous-estime.
- Pas encore : détection langues multiples par message, topics/sujets générateurs de réponse, voice notes transcription.
- Les patterns manuels riches (discourse_flirt_machine, discourse_politeness_pattern) ne sont PAS générés par le script — à faire à la main par contact important, types libres acceptés par la table.
