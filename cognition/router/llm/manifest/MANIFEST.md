# walter-llm

**Role.** Executes the model calls of authorised consumers (the engine, Context, Memory, Skills…) through the Router's
postes. A consumer names a poste (`model` = task), never a provider model; the gateway resolves the route, reads the
provider key through its vault grant, and applies the request's cache layout, reasoning effort and fallbacks between
providers of the same model.

**Organisation.** Gateway `127.0.0.1:8894` (OpenAI-compatible; also `/v1/decisions` for the Router's decision chain,
`/v1/rerank`, `/v1/balance`), subscription transports (Claude, ChatGPT/Codex, Antigravity), a test budget for paid
test calls, CLI `walter-llm call` (one exact model/provider, no implicit retry).

**Use.** Agents do not call it directly: the engine uses it for its own turns, and `walter_run` / `walter_route` reach
models through the Router. Live state: `walter_health`, `walter-llm test-budget`.
