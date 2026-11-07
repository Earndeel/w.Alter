# Chat ID lookup (quand getUpdates est bloqué)

Si le gateway Hermes tourne déjà en long polling, l'appel `getUpdates` à l'API Telegram retourne `409 Conflict: terminated by other getUpdates request`.

**Solution** : récupérer le chat_id via le fichier d'approbation stocké dans les snapshots :

```bash
cat /root/.hermes/state-snapshots/*/pairing/telegram-approved.json
# → {"1146774717": {"user_name": "Lucas", "approved_at": ...}}
```

**Chat ID connu de Monsieur** : `1146774717`

**Envoi direct** (contourne le gateway) :

```bash
source /root/.hermes/.env 2>/dev/null
curl -sS -F "chat_id=1146774717" \
  -F "photo=@/absolute/path/to/image.png" \
  -F "caption=Description" \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendPhoto"
```

Réponse confirmée : `{"ok":true,"result":{"message_id":751,...}}`
