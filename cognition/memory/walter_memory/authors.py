"""Who wrote an event (27/11/2026, Monsieur): Memory keeps four separate things about it — the technical source
(core.events.source, its kind in core.sources), the communication channel (payload.chat.network / source_account),
the author (core.events.actor_identity_id → core.source_identities) and the author's nature, one of KINDS.

The nature is a property of the source identity, kept in its existing `attributes` (attributes.author +
attributes.author_rule): decided at write time by events.upsert_identity (a connector that knows better declares
it: actor attributes {"author": …, "author_rule": "declared"}), and for the stored identities by
classify_all(). No event is rewritten (append-only history). Rules are deterministic and configured in
config/authors.toml (+ the instance's additions); an identity they do not recognise is a human, as before.

Readers: events.get_events(source="people") = exchanges with humans on any channel (an author that is not human, or a
one-to-one conversation with one, is left out); source="agents" = the conversations with W.Alter and other agents;
social.resolve_identities types the entities from it (W.Alter → the existing `agent` entity type)."""
from __future__ import annotations

import re
import subprocess
import tomllib
from functools import lru_cache
from pathlib import Path

KINDS = ("human", "walter", "agent", "bot", "service")
NOT_HUMAN = tuple(k for k in KINDS if k != "human")
MODULE_CONFIG = Path(__file__).resolve().parent.parent / "config" / "authors.toml"


def _merge(base: dict, extra: dict) -> dict:
    out = {k: dict(v) if isinstance(v, dict) else v for k, v in base.items()}
    for section, values in extra.items():
        if not isinstance(values, dict):
            continue
        cur = out.setdefault(section, {})
        for k, v in values.items():
            cur[k] = list(dict.fromkeys([*(cur.get(k) or []), *v])) if isinstance(v, list) else v
    return out


@lru_cache(maxsize=1)
def settings() -> dict:
    cfg = tomllib.loads(MODULE_CONFIG.read_text())
    try:
        found = subprocess.run(["walter", "instance", "path"], capture_output=True, text=True, timeout=10).stdout.strip()
        extra = Path(found) / "config" / "memory" / "authors.toml" if found else None
        if extra and extra.is_file():
            cfg = _merge(cfg, tomllib.loads(extra.read_text()))
    except (OSError, subprocess.SubprocessError, tomllib.TOMLDecodeError):
        pass          # the module's rules alone: W.Alter's own network accounts then read as bots
    return cfg


@lru_cache(maxsize=1)
def agent_sources() -> frozenset[str]:
    """Technical sources that are agent runtimes (core.sources.kind = 'agent')."""
    from .db import connection
    try:
        with connection() as conn:
            return frozenset(r["source"] for r in conn.execute("select source from core.sources where kind = 'agent'"))
    except Exception:  # noqa: BLE001
        from .search import AGENT_SOURCES
        return frozenset(AGENT_SOURCES)


def classify(source: str, actor: dict, cfg: dict | None = None) -> tuple[str, str]:
    """(nature, rule) of one source identity — actor fields: account, external_id, display_name, handles, emails,
    is_self."""
    cfg = cfg or settings()
    ext = str(actor.get("external_id") or "")
    name = (actor.get("display_name") or "").strip()
    handles = [str(h) for h in (actor.get("handles") or {}).values() if h]
    account = str(actor.get("account") or "")
    low = {h.lower() for h in handles}
    if actor.get("is_self"):
        return "human", "owner"
    walter = cfg.get("walter", {})
    if low & {h.lower() for h in walter.get("handles", [])}:
        return "walter", "walter_handle"
    if source in agent_sources():
        if ext in walter.get("external_ids", []):
            return "walter", "walter_runtime"
        if ext in cfg.get("human", {}).get("external_ids", []):
            return "human", "owner_in_agent_source"
        return "agent", "agent_runtime"
    svc = cfg.get("service", {})
    if any(re.search(p, ext) for p in svc.get("external_id_patterns", [])):
        return "service", "service_account"
    if any(re.search(p, ext.lower()) for p in svc.get("email_patterns", [])) or any(
            re.search(p, e.lower()) for e in actor.get("emails") or [] for p in svc.get("email_patterns", [])):
        return "service", "automatic_sender"
    if name in cfg.get("agent", {}).get("display_names", []):
        return "agent", "network_assistant"
    if name in svc.get("display_names", []):
        return "service", "network_account"
    suffix = cfg.get("bot", {}).get("telegram_handle_suffix")
    if suffix and account.startswith("telegram") and any(h.endswith(suffix) for h in low):
        return "bot", "telegram_bot_username"
    return "human", "default"


def decide(source: str, identity: dict, cfg: dict | None = None) -> tuple[str, str]:
    """(nature, rule) of a stored identity: what its connector declared (attributes author + author_rule "declared")
    wins, else the rules."""
    a = identity.get("attributes") or {}
    if a.get("author_rule") == "declared" and a.get("author") in KINDS:
        return a["author"], "declared"
    return classify(source, identity, cfg)


def classify_all(*, dry_run: bool = False) -> dict:
    """(Re)decide the nature of every stored identity — identity rows only, never an event. Idempotent: an identity
    whose nature is unchanged is not written."""
    from collections import Counter
    from .db import connection
    cfg, counts, changed = settings(), Counter(), []
    with connection() as conn:
        rows = conn.execute("""select identity_id::text, source, account, external_id, display_name, handles, emails,
                                      is_self, attributes from core.source_identities""").fetchall()
        for r in rows:
            kind, rule = decide(r["source"], r, cfg)
            counts[kind] += 1
            a = r["attributes"] or {}
            if a.get("author") != kind or a.get("author_rule") != rule:
                changed.append((kind, rule, r["identity_id"]))
        if not dry_run and changed:
            conn.cursor().executemany(
                """update core.source_identities set attributes = attributes
                       || jsonb_build_object('author', %s::text, 'author_rule', %s::text) where identity_id = %s""",
                changed)
    return {"identities": len(rows), "by_author": dict(counts), "changed": len(changed), "dry_run": dry_run}


_threads: tuple[tuple, dict[str, str]] | None = None


def nonhuman_threads(conn) -> dict[str, str]:
    """Memoised per process until a non-human identity is added or writes again (its last_seen moves): the scan below
    costs about half a second, the key a few milliseconds."""
    global _threads
    key = tuple(conn.execute("""select count(*) n, max(last_seen) last from core.source_identities
                                where attributes->>'author' = any(%s)""", (list(NOT_HUMAN),)).fetchone().values())
    if _threads is None or _threads[0] != key:
        _threads = (key, _scan_nonhuman_threads(conn))
    return _threads[1]


def _scan_nonhuman_threads(conn) -> dict[str, str]:
    """thread_id → nature of the other side, for the one-to-one conversations where nobody but non-human authors
    writes to the owner (a bridge notice inside a real conversation does not turn it into a bot's): what the owner
    writes there is not an exchange with a person either."""
    return {r["thread_id"]: r["kind"] for r in conn.execute(
        """with c as (select e.source, e.thread_id, mode() within group (order by i.attributes->>'author') kind
                      from core.source_identities i join core.events e on e.actor_identity_id = i.identity_id
                      where i.attributes->>'author' = any(%s) and e.thread_id is not null
                        and e.event_type = 'message.received' and e.payload->'chat'->>'type' = 'single' group by 1, 2)
           select c.thread_id, c.kind from c
           where not exists (select 1 from core.events h join core.source_identities hi on hi.identity_id = h.actor_identity_id
                             where h.source = c.source and h.thread_id = c.thread_id and h.event_type = 'message.received'
                               and not hi.is_self and coalesce(hi.attributes->>'author', 'human') = 'human')""",
        (list(NOT_HUMAN),))}
