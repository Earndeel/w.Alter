"""A model named by the owner (« avec Opus 5.5 chez Kie ») runs as named, or the answer says why it cannot: never a
silent substitute. The name is resolved like the boards' names (provider ids, router ids, aliases, display names);
`model/variant` sets the reasoning level (gpt-6-1-sol/high)."""
from __future__ import annotations

from typing import Any

from walter_router.analysis import identity
from walter_router.analysis import select as sel
from walter_router.serve import execution

PROVIDERS = {"openrouter": "openrouter", "kie": "kie", "kie.ai": "kie", "kie-codex": "kie", "codex": "codex",
             "openai-codex": "codex", "chatgpt": "codex", "arnict": "arnict", "flow": "google-flow",
             "google-flow": "google-flow"}
DEFAULT_TASK = {"chat": "general", "image": "text_to_image", "video": "text_to_video", "audio": "tts", "music": "music"}


def resolve(conn, name: str) -> tuple[str, str] | None:
    """(model_id, variant) of a name as the owner or an agent writes it, or None."""
    raw = name.strip()
    variant = ""
    head, sep, tail = raw.rpartition("/")
    if sep and tail.lower() in execution.REASONING:
        raw, variant = head, tail.lower()
    row = conn.execute("""select o.model_id from models.offers o join models.latest_snapshots s using (snapshot_id)
                          where lower(o.offer_key) = lower(%s) limit 1""", (raw,)).fetchone()
    if row:
        return row["model_id"], variant
    for ns in ("openrouter", "aa"):
        mid, v = identity.normalize(ns, raw, raw)
        if conn.execute("select 1 from models.canonical where model_id = %s", (mid,)).fetchone():
            return mid, variant or v
    row = conn.execute("""select model_id from models.aliases where lower(external_key) = lower(%s) limit 1""",
                       (raw,)).fetchone() or \
        conn.execute("""select model_id from models.canonical where lower(display_name) = lower(%s) limit 1""",
                     (raw,)).fetchone()
    return (row["model_id"], variant) if row else None


def named(conn, model: str, provider: str | None = None, task: str | None = None) -> dict[str, Any]:
    """The decision for a named model (and provider): its task, and for text the execution routes at that provider
    only. `mode: none` with the reason when it cannot run as named."""
    found = resolve(conn, model)
    if not found:
        return {"mode": "none", "named": {"model": model, "provider": provider},
                "error": f"modèle inconnu du router : {model}"}
    model_id, variant = found
    prov = PROVIDERS.get((provider or "").strip().lower()) if provider else None
    if provider and not prov:
        return {"mode": "none", "model_id": model_id, "named": {"model": model, "provider": provider},
                "error": f"fournisseur inconnu : {provider} (connus : {', '.join(sorted(set(PROVIDERS.values())))})"}
    offers = sel.load_offers(conn, sel.latest_snapshots(conn)).get(model_id, [])
    t = conn.execute("select task, interface from models.tasks where task = %s", (task,)).fetchone() if task else None
    interfaces = [o["interface"] for o in offers]
    interface = t["interface"] if t else ("chat" if "chat" in interfaces else next(
        (i for i in interfaces if i in DEFAULT_TASK), None))
    if interface is None:
        return {"mode": "none", "model_id": model_id, "named": {"model": model, "provider": provider},
                "error": f"{model_id} : aucune offre chez nos fournisseurs"}
    available = sorted({o["provider"] for o in offers if o["interface"] == interface})
    out = {"task": t["task"] if t else DEFAULT_TASK[interface], "mode": "delegate", "source": "named",
           "model_id": model_id, "variant": variant, "provider": prov,
           "named": {"model": model, "provider": provider}, "available_at": available}
    if prov and prov not in available:
        return {**out, "mode": "none",
                "error": f"{model_id} n'est pas proposé chez {prov} (disponible : {', '.join(available) or 'nulle part'})"}
    if interface == "chat":
        routes = [r for r in execution.routes(conn, model_id, variant) if not prov or r["provider"] == prov]
        if not routes:
            return {**out, "mode": "none",
                    "error": f"{model_id} : aucune route exécutable" + (f" chez {prov}" if prov else "")}
        out["execution"] = routes
    return out
