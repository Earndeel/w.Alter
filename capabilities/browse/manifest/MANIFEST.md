# Walter Browse

**Role.** Web access for every agent: search, read and extract with the right depth chosen by the engine (direct
request, static HTML, Scrapling, Camoufox, Webtop), and act on a signed-in site as {{owner.address}}. The agent
describes what it wants, not how to get it.

**Organisation.** A common engine with profiles learned per domain and a result cache; a persistent Camoufox browser
(`:9377`) and Chromium (CloakBrowser, `:9378`) when a site requires it, both visible and controllable by
{{owner.address}}; network exits chosen by the engine (the owner's machine, a France exit, per-country exits on
demand).

**Tools**
- Search, read, extract: `walter_browse(query=… | url=…)` (`content_only=true` to read a page; `objective`,
  `expected_fields` to extract).
- Act signed in: `browser_session(site)` (cookies injected server-side, metadata only returned; `browser_sites` lists
  the sites), then the local CLI `walter-browser -s <session> new|nav|snap|click|clickxy|ktype|shot|eval|upload|fetch|close`;
  call `browser_session` again when a login page appears. `engine="chromium"` when a site needs Chromium.

**Rules**: read the web only through `walter_browse` (it chooses the network exit), never `curl`/`wget` from the
shell; never extract cookies yourself; human keystrokes, never programmatic form filling.
