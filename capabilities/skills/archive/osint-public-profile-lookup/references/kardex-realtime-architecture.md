# Architecture Kardex temps réel (v1, déployée le 2026-08-23)

## Flux
```
Beeper Desktop (Mac) ──index.db──> beeper_watch.py [launchd com.walter.kardex-watch]
    │  poll 3s, snapshot WAL-safe, offset persistant ~/.kardex/.kardex_watcher_state.json
    ▼ POST HMAC X-Hub-Signature-256 + event_type=kardex.ingest
VPS gateway :8644 /webhooks/kardex-ingest
    ▼ route script (PAS de prompt LLM)
~/.hermes/scripts/kardex_webhook_ingest.py → kardex_ingest.py (SQL pur, idempotent par event_id)
    ├─ imprime [SILENT] → aucun run LLM (cas nominal)
    └─ imprime JSON si rooms non mappées → run agent léger pour créer le contact
    ▼
cron */15min : kardex_semantic_extract.py (Gemini 3.6 Flash gratuit via OpenRouter)
    ├─ batch 40 msgs non marqués raw->>'semantic_done'
    ├─ claims avec citation obligatoire sinon rejetés, status='proposed'
    └─ recalcule kardex_comm_metrics.py pour les contacts touchés
```

## Pièges rencontrés (TOUS résolus)
1. **API Beeper plafonne à 20 msgs/page** quel que soit `limit` → paginer avec `cursor=` (pas beforeSortKey/sinceSortKey qui renvoient la même page).
2. **Signature webhook** : header `X-Hub-Signature-256: sha256=<hmac(body, secret)>` (gateway/platforms/webhook.py:1036). 401 = mauvais header ou secret.
3. **Filtre d'événement** : payload DOIT contenir `event_type` matching la subscription `--events`, sinon 200 "ignored" silencieux.
4. **Route script** : chemin DOIT être sous `/root/.hermes/scripts` sinon rejeté ("resolves outside"). Le script lit stdin JSON ; `[SILENT]` = drop sans LLM ; JSON imprimé = devient le prompt d'un run agent.
5. **attachment_types est un ARRAY PG** : passer une liste Python directement, pas json.dumps.
6. **Modèle OpenRouter** : gemini-flash-1.5 n'existe plus → `google/gemini-3.6-flash` (gratuit).
7. launchd : `launchctl kickstart -k gui/501/...` pour restart ; logs dans ~/.kardex/watch.{log,err}.

## Fichiers
- Mac : ~/.kardex/beeper_watch.py + ~/Library/LaunchAgents/com.walter.kardex-watch.plist
- VPS : /root/.hermes/scripts/{kardex_webhook_ingest,kardex_ingest,kardex_semantic_extract}.py
- Sources : /root/hermes/kardex/
- Secrets : subscription secret dans plist Mac (KARDEX_WEBHOOK_SECRET) + /root/hermes/kardex/.webhook_secret

## Usage quotidien (W.Alter)
- Contexte avant réponse : `python3 /root/.hermes/scripts/kardex_context.py <nom|handle|id> [n_msgs]`
  → brief compact: identité, faits stratégiques, claims confirmés, open loops, style chiffré, derniers messages.
- Nouveau contact Beeper : le webhook émet kardex.new_contact → créer contact+channel puis les msgs suivants couleront.
- Claims auto = status 'proposed' → validation humaine en session avant passage en 'confirmed'.
