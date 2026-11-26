# Walter Browse — detailed guide

## Purpose
Get data from the web as quickly and reliably as possible, and act on a signed-in site as {{owner.address}} when
needed. The engine chooses its depth (direct request, static HTML, Scrapling, Camoufox, Webtop) according to the
request and the site; the agent describes what it wants, not how to get it.

## How to use it
1. **Search / read / extract**: `walter_browse(query=… | url=…)`. Read a page: `content_only=true`. Structured
   extraction: `objective`, `expected_fields`, `required_fields`, `min_records`.
2. **Act signed in as {{owner.address}}**: `browser_session(site, session)` opens or refreshes a Camoufox session with
   their cookies, injected server-side (only metadata comes back); `browser_sites` lists the sites. Then drive it with
   `walter-browser -s <session> new|nav|snap|click|clickxy|ktype|shot|eval|upload|fetch|close`. If the site needs
   Chromium: `browser_session(..., engine="chromium")` / `walter-browser -e chromium …` on the session's first call
   (CloakBrowser, same API, same rules); the session then keeps its engine.
3. Call `browser_session` again as soon as the site shows a login page.
4. **Talk to a chat web service**: through the Router (`walter_web`), which picks the recipe; in code,
   `walter_browse.converse(host, capability, message, conversation=…, request_id=…, model=None, files=None)`. The
   recipe is learned on the first pass and replayed without a model afterwards.

## Organisation
| Part | Role |
|---|---|
| `walter_browse/` (facade), `runtime/universal_router.py` | Common engine: path choice, identical semantic extraction contract on every path |
| `runtime/profile_index.py`, `result_cache.py` | Profiles learned per domain, result cache; state in the instance (`state/browse`) |
| Camoufox `:9377` (X display `:101`) | W.Alter's persistent browser; {{owner.address}} sees and drives it through Selkies (tailnet) |
| Chromium `:9378` (CloakBrowser, same display) | Second engine, for sites that require Chromium; same API and rules |
| Network exit `walter-exit-default` | By default the owner's machine while its connection is up, else the France WireGuard exit, automatically; `walter-wg-exit use <exit>` for per-country exits |
| `runtime/conversation.py`, `walter_browse/converse.py` | Conversational capabilities: `kind=conversation` recipes, tab and conversation reused, real keyboard paste |

## Interfaces
| Need | MCP | CLI |
|---|---|---|
| Search / extraction | `walter_browse` | — |
| Signed-in session | `browser_session`, `browser_sites` | `walter-browser login SITE` |
| Driving | — | `walter-browser -s <session> …` |
| Chat web service | `walter_web` (Router) | `runtime/conversation.py MESSAGE --host … --capability …` |

## Rules and limits
- Never extract cookies yourself; a new site is declared in `browser_sites.json` (no secret).
- {{owner.address}}'s cookies are accepted only by a session that leaves through their network exit; if no such exit
  is available, signed-in connections are refused (never the server's IP).
- Real keystrokes, never programmatic filling; a message is pasted with a real Ctrl+V; frozen device fingerprint.
- A chat web service is enabled only by {{owner.address}} (Router `web_services` table), within its terms of use; no
  circumvention of access restrictions.
