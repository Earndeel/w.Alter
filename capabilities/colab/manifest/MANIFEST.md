# Walter Colab

**Role.** Occasional remote compute on Google Colab for jobs the server cannot run (GPU work), through the official
Colab MCP and the Colab Files interface, with results saved back before the runtime is deleted.

**Rules.** No purchase, no keep-alive, no permanent remote server, no multiple accounts, no Google refresh token in the
notebook. Zero new purchase is not zero compute units: an allocated GPU consumes included units, even while preparing.
**GPU jobs (T4/L4/A100) are currently blocked** by the canonical controller until a real validation of prepared
artefacts exists; CPU jobs work. Never bypass the lock with low-level scripts.

**Interfaces.** CLI `on_demand.py` (bridge, `/walter/capabilities/colab`), Colab MCP server (`mcp/`). Detail and
preparation conditions: `/walter/capabilities/colab/RUNBOOK.md`.
