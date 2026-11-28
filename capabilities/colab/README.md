# walter-colab — calcul distant ponctuel

| | |
|---|---|
| **Rôle** | Préparer et exécuter des travaux de calcul distant qualifiés sur Google Colab (GPU à la demande, jamais en veille), avec sauvegarde des résultats avant libération. |
| **Propriétaire** | walter-colab (`/walter/capabilities/colab`). |
| **État** | **implemented** (constat du 09/11/2026) : pas de service ; le contrôleur refuse encore tout job GPU (T4/L4/A100) tant qu'un artefact préparé n'a pas été validé ([RUNBOOK.md](RUNBOOK.md) § interverrouillage). |
| **Ne fait pas** | Acheter des unités, garder un jeton Google dans le notebook, maintenir un serveur distant ou un keep-alive, utiliser plusieurs comptes ; remplacer en silence un GPU par un worker gratuit ou une API payante. |
| **Contrats** | [contracts/colab.json](contracts/colab.json) ; CLI `on_demand.py` ; MCP Colab officiel ([mcp/](mcp/)). |

Composants : `bridge.py` (pont Colab), `on_demand.py` (contrôleur), `transfer.py` / `drive_store.py` (transport des
artefacts et résultats), `mcp/` (serveur MCP Colab). Procédure, contrat économique et conditions de déverrouillage du
GPU : [RUNBOOK.md](RUNBOOK.md).
