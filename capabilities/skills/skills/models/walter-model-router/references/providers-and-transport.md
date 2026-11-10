# walter-model-router — Native text execution and provider failover, the Claude subscription transport, diagnosing a Kie outage without downgrading its media, adding a Bitwarden-backed provider.

Moved verbatim from SKILL.md on 2026-11-01.

## Native text execution and provider failover (2026-10-23)
`walter-router run` now executes text natively, through `walter-llm call` (one exact provider/model). No Hermes subprocess or hidden model fallback is used for text. Only providers of the selected model are tried; if all fail, report the failure without substituting another model. The conversation and completed tools survive provider changes. Inspect `routed.attempts` (actual provider, model, response id), `tools`, and `runtime=walter-router`. When `user_notification_required` is true, ALWAYS relay `user_notice` to the user. This also applies when execution fails. Named provider restrictions remain explicit.
Verified on the installed version: 168 tests passed; `walter check` passed. A real coding/tool run received RateLimitError from Kie, kept Claude Opus 5.5, succeeded on OpenRouter with two recorded response ids and a terminal assertion/checksum. Backup of prior source is retained on the host; no Hermes core or global configuration was modified.

## Claude subscription transport (2026-10-27)
The optional provider `claude-pro` is now a Walter Router route, not a direct Hermes provider. Read `docs/CLAUDE-SUBSCRIPTION.md` under `walter path router` for configuration and operational limits. The verified model allowlist belongs to the instance, not the shared code; catalogue presence alone never proves generation or tool capability.

The official native client contributes authenticated transport and a validated technical billing attribution only. The bridge forwards caller-owned messages, tools and parameters; no native Agent SDK identity, machine context, CLAUDE.md or native tools. Real responses/tool calls return only to Walter's own tool loop. The CLI gets a synthetic tool-free acknowledgement. Streaming, exact model identity and cancellation are covered by the transport. A caller requiring this subscription may use `provider=claude-pro`; no provider/model fallback is added by the adapter.

The `claude-subscription` grant is renewed only by Walter Secrets (opaque token expiry, interprocess lock, atomic rotation). Never extract or print credentials. `walter-secret grants claude-subscription` exposes metadata only. `research --source claude_pro` refreshes the qualified catalogue; the existing quota worker reads real five-hour/weekly vendor meters (`claude_usage_api`) instead of transcript estimates. Actual bridge token metadata are distinct from the CLI's synthetic acknowledgement and local list-price estimates.

After changing the instance's gateway configuration, restart `walter-llm`; do not change a global CLI or model favourite merely to provision this optional transport. Do not force expiry or rotate persistent credentials just to test renewal without specific authorization. Publishing library metadata is a separate external write: prepare a local preview and obtain authorization if the approval reviewer rejects publication. Neither a blocked forced-renewal test nor a blocked publication prevents the installed Router route from being validated independently.

## Diagnostiquer une panne Kie sans déclasser ses médias

- Avant toute modification, lire `git -C /walter/cognition/router status --short` et identifier les fichiers travaillés par les autres sessions. Ne pas les modifier ni les commiter sans autorisation explicite. Le guardian attend lorsque des changements non commités empêchent son intervention.
- Lancer `timeout 90 walter-router health` et distinguer les services Kie : Claude, Codex et médias. Une panne de l’API Claude ne prouve pas une panne des médias.
- Inspecter `serve/execution.py` pour les sondes et `serve/media_exec.py` pour leur effet sur le choix du fournisseur. Conserver `kie` pour Claude et `kie-media` pour les médias ; ne pas utiliser l’état Claude pour déclasser les images ou vidéos.
- Pour les médias, vérifier le compte et le crédit sans lancer de génération payante. Pour les réponses textuelles en streaming, HTTP 200 et un corps non vide ne suffisent pas : vérifier la présence du contenu attendu et afficher l’erreur du fournisseur lorsqu’elle est disponible. Une réponse SSE peut se terminer sans message utile.
- Vérifier le comportement avec `cd /walter/cognition/router` puis `venv/bin/python -m pytest -q -p no:cacheprovider tests/test_media_exec.py`. Contrôler aussi le fournisseur réellement choisi : une sonde médias saine rend Kie éligible, mais le prix peut toujours favoriser OpenRouter.
- Après les corrections et leurs commits, lancer `walter-router-guardian run --no-agent --no-notify`, puis `walter-router-guardian status` pour vérifier les incidents sans déclencher de réparation par agent ni de notification.
- Si le guardian analyse les sorties pytest, préserver les identifiants paramétrés contenant des espaces : utiliser une capture de l’identifiant complet, pas `\S+`.

## Add a provider backed by Bitwarden and validate it

When adding a provider to Walter Router, store the API key in Bitwarden through `walter-secret`, declare the key in `/instances/monsieur/config/secrets/walter-secrets.toml`, and keep the secret out of `.env` files and repository configuration. For Venice, use the vault item `W.Alter · venice` and the model `deepseek-v4-1-flash-1017-uncensored`.

Inspect the existing provider and secret mechanisms first:

```bash
cd /walter/cognition/router
sed -n '240,330p' llm/gateway.py
cat config/providers.json
cd /walter/core/security/secrets
sed -n '96,150p' walter_secrets/vault.py
walter-secret --help
```

Store or update the key by piping it through standard input; never put the value in a command argument or file:

```bash
printf '%s' '<VENICE_API_KEY>' | walter-secret store 'W.Alter · venice' --kind api_key --stdin --uri https://api.venice.ai
```

Add the corresponding declared secret mapping in `/instances/monsieur/config/secrets/walter-secrets.toml`, then verify that the mapping resolves without printing the secret:

```bash
walter-secret search venice
python3 -c 'from walter_secrets import mapping; print(mapping.entry("VENICE_API_KEY"))'
```

Add Venice using the same provider configuration and gateway adapter conventions as the existing OpenAI-compatible providers. Validate the JSON and run the router checks:

```bash
cd /walter/cognition/router
python3 -I -c 'import json; json.load(open("config/providers.json")); print("json ok")'
timeout 300 walter check
```

Restart the gateway before live validation and confirm the service and health endpoint:

```bash
systemctl restart walter-llm
systemctl is-active walter-llm
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8894/health
```

Test the exact model through the native Walter path and run the provider probe:

```bash
printf '%s\n' '{"route":{"provider":"venice","model":"deepseek-v4-1-flash-1017-uncensored"},"messages":[{"role":"user","content":"Réponds seulement: OK"}],"timeout":60}' | timeout 120 walter-llm call
cd /walter/cognition/router
timeout 300 walter-router probe --provider venice
```

Regenerate and check generated documentation after changing provider metadata:

```bash
walter-router docs --write
timeout 60 walter-router docs --check
```

Run the relevant tests, recording unrelated pre-existing failures separately:

```bash
timeout 900 venv/bin/python -m pytest -q --ignore=tests/test_gateway_telemetry.py
timeout 600 venv/bin/python -m pytest -q tests/test_documentation.py
```

Before declaring success, confirm that the live call, native `walter-llm` call, provider probe, health endpoint, and JSON/config checks pass. Check `walter check` for neutrality failures: generated reference files and router/LLM source can contain owner-specific markers after documentation generation, so inspect the reported files and remove any newly introduced private names from shipped module files. Do not overwrite unrelated uncommitted work; inspect `git diff --stat` and preserve existing changes.

