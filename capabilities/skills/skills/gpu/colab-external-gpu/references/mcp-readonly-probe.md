# Éprouver le MCP officiel sans allouer de runtime

## Périmètre

- Exporter le checkout officiel dans un scratch dédié avant d'installer ses dépendances ; le clone partagé reste intact et ses hooks/configuration Git ne changent pas.
- Lire le `requires-python` du checkout et fournir une version compatible ; pour un paquet qui exige >=3.13, Python système 3.12 ne suffit pas.
- Isoler `UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR`, `TMPDIR`, la venv et les journaux dans le scratch ; une installation ad-hoc ne doit pas ajouter de serveur à la configuration Hermes.
- Utiliser le SDK officiel Python `mcp.ClientSession` avec `mcp.client.stdio.stdio_client` pour vérifier `initialize`, `send_ping` et `list_tools` ; une installation réussie seule ne prouve pas une réponse MCP.
- Ne jamais appeler `open_colab_browser_connection` lors d'un diagnostic sans interaction autorisée ; cet outil lance réellement le navigateur et attend une connexion frontend.
- Lire les réponses réelles plutôt qu'inventer les outils notebook ; hors connexion, le pont injecte seulement `open_colab_browser_connection`, et les outils connectés viennent du frontend, pas d'un registre statique dans le clone.
- Distinguer les deux secrets : `mcpProxyToken`/`access_token` est le jeton local aléatoire du pont, pas OAuth Google ; ne journaliser aucune valeur de jeton.
- Vérifier l'écoute loopback pendant le test et sa disparition après fermeture du client ; ne conserver ni daemon ni tunnel après un spike.
- Qualifier les tests WebSocket amont de tests locaux/unitaires ; même tous réussis, ils ne prouvent pas une connexion au frontend Google ou une exécution GPU.
- Ne pas déduire un backend REST des dépendances OAuth/Jupyter déclarées ; inspecter les imports et appels réels de `src/colab_mcp`.

## Préparation isolée

Adapter les chemins à un clone découvert et à un scratch exclusif. Cette forme a été exercée sur Linux ARM avec le checkout officiel et son lockfile :

```sh
S=/root/.hermes/cache/scratch/colab-api-spike
mkdir -p "$S/repo" "$S/logs" "$S/tmp"
git -C /root/.hermes/cache/scratch/colab-probe/official-mcp archive HEAD | tar -x -C "$S/repo"
UV_CACHE_DIR="$S/uv-cache" UV_PYTHON_INSTALL_DIR="$S/python" TMPDIR="$S/tmp" \
  uv sync --project "$S/repo" --python 3.13 --frozen
```

Créer avec l'outil d'écriture un client Python de test, sans implémenter de faux backend. Son noyau protocolaire est :

```python
from datetime import timedelta
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(
    command=str(scratch / "repo/.venv/bin/colab-mcp"),
    args=["--log", str(logdir)],
    cwd=str(scratch / "repo"),
    env={"TMPDIR": str(scratch / "tmp"), "BROWSER": "/bin/false"},
)
with stderr_file.open("w") as errlog:
    async with stdio_client(params, errlog=errlog) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=20)) as session:
            initialized = await session.initialize()
            await session.send_ping()
            tools = await session.list_tools()
            assert [tool.name for tool in tools.tools] == ["open_colab_browser_connection"]
            # Sauver les model_dump(mode="json", by_alias=True) réellement retournés.
```

Créer les répertoires de journaux avant le serveur ; `--log` ne les crée pas. Ajouter un handler `ServerNotification` quand le diagnostic doit supporter les changements d'outils. Ne pas imposer le toolset déconnecté à une connexion navigateur déjà autorisée.

Exécuter le client avec la venv du checkout puis les tests amont en cwd du repo :

```sh
TMPDIR="$S/tmp" "$S/repo/.venv/bin/python" "$S/probe_stdio.py"
cd "$S/repo"
TMPDIR="$S/tmp" .venv/bin/python -m pytest tests --junitxml="$S/pytest-results.xml"
```

## Symboles à vérifier

- `colab_mcp.__init__.main_async` : monte le proxy puis exécute le serveur MCP en stdio.
- `colab_mcp.session.ColabSessionProxy.start_proxy_server` : crée WS et `FastMCPProxy`, injecte l'outil d'ouverture.
- `ColabProxyClient.client_factory` : client MCP vide hors connexion, client frontend une fois prêt.
- `check_session_proxy_tool_fn` : URL Colab avec fragment `mcpProxyToken`/`mcpProxyPort`.
- `ColabTransport.connect_session` : `ClientSession` sur les streams WS.
- `ColabProxyMiddleware.on_message` : état observé à chaque message et `send_tool_list_changed` à la transition.
- `ColabWebSocketServer.__aenter__` : `localhost`, port système, origins Colab et sous-protocole `mcp`.
- `ColabWebSocketServer._validate_authorization` : jeton local par bearer ou query ; jamais une admission API Google.

Le modèle officiel exige navigateur et client local sur le même appareil. Un serveur démarré sur une VM n'atteint pas spontanément un onglet Mac. Garder l'API REST sur allowlist comme voie headless distincte, conformément à `official-access.md`.
