"""Telegram side of the alerts: one message per piece of news with its buttons (2026-10-16 owner's format: header
« W.Alter Router — dd/mm », the router's category named, short readable lines, OpenRouter price, decision models on
three axes with a recommendation for his stack, plan news), sent through Walter's Telegram door
(`walter-telegram send`, core/interfaces/telegram, since 2026-11-10); the clicks come back through it as
`walter-router button` (alerts already sent by Hermes' bot keep their Hermes plugin handler)."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone

from walter_router import instance
from walter_router.analysis import catalog
from walter_router.analysis import media
from walter_router.analysis.alerts import HERMES, pending

ROLE_LABELS = {"value": "ratio", "budget": "budget", "action": "action", "default": "défaut", "premium": "premium",
               "ugc": "UGC"}


def _challenger_line(conn, a: dict) -> str:
    e = a["evidence"]
    if "challenger" in e:  # alert recorded before 004 (single board)
        return f'[{a["alert_id"]}] {e["task_label"]} : {e["challenger"]} dépasse {e["pinned"]} (+{e["delta"]:.0f})'
    if "boards" not in e:
        return f'[{a["alert_id"]}] {a["task"]} : ton favori {e.get("pinned")} n\'apparaît dans aucun classement.'
    task = conn.execute("select interface, modes from models.tasks where task = %s", (a["task"],)).fetchone()
    c = catalog.card(conn, a["subject"], task["interface"], task["modes"])
    pinned = catalog.card(conn, e["pinned"], task["interface"], task["modes"])["name"]
    role = ROLE_LABELS.get(e.get("role"), "")
    gains = ", ".join(f'+{b["delta"]:.0f} {_short_board(name)} #{b["rank"]}' for name, b in e["boards"].items())
    return (f'[{a["alert_id"]}] {e["task_label"]}{f" ({role})" if role else ""} : {catalog.icon(c)} {c["name"]} dépasse {pinned} '
            f'({gains}) — {catalog.price_text(c)} — {", ".join(catalog.PROVIDERS.get(p, p) for p in c["providers"]) or "aucun provider"}')


def _short_board(name: str) -> str:
    return name.replace("text_to_", "t2").replace("image_to_", "i2").replace("_", " ")


def _fr(x, digits: int) -> str:
    return f"{x:.{digits}f}".replace(".", ",") if x is not None else "?"


def _head(c: dict) -> str:
    short = media.short_modes(c["modes"]) if c.get("modes") else ""
    modes = f' · {short}' if short else ""
    return f'{catalog.icon(c)} {c["name"]}{modes}'


def _money_line(c: dict) -> str:
    prov = ", ".join(catalog.PROVIDERS.get(p, p) for p in c.get("providers") or [])
    return f'💰 {catalog.price_text(c)}' + (f' — {prov}' if prov else "")


def _why(e: dict) -> str | None:
    return ("🔎 " + " ; ".join(str(w) for w in e["why"][:3])) if e.get("why") else None


def _plan_block(a: dict) -> list[str]:
    """2026-10-22: a billing e-mail differs from the declared plans."""
    e = a["evidence"]
    amount = f' — {_fr(e["amount"], 2)} {"€" if e.get("currency") == "EUR" else "$"}' if e.get("amount") else ""
    if e.get("news"):   # a new benefit or change on a plan the owner has (2026-10-22)
        return [f'💳 {e.get("plan")} — nouveauté', f'📰 {e.get("title")}', f'{e.get("quote", "")[:380]}' if e.get("quote") else None,
                f'🔗 {e.get("source")}' + (f' — {e["url"]}' if e.get("url") else "")]
    if e.get("action") == "none":
        return ["💳 Abonnements — fin d'offre", f'📅 {e.get("vendor")} {e.get("plan")} : {e.get("text")}']
    return ["💳 Abonnements — changement repéré dans un mail", f'📧 {e.get("vendor")} {e.get("plan") or ""}{amount}'
            f' ({e.get("mail_date") or "date inconnue"})', f'💡 Proposition : {e.get("text")}',
            f'« {e.get("quote", "")[:160]} »']


def _block(conn, a: dict) -> list[str]:
    e = a["evidence"]
    if a["kind"] == "plan_change":
        return _plan_block(a)
    task = conn.execute("select label, interface, modes from models.tasks where task = %s", (a["task"],)).fetchone() \
        if a["task"] else None
    if a["kind"] == "challenger" and "boards" in e:
        c = catalog.card(conn, a["subject"], task["interface"], task["modes"])
        pinned = catalog.card(conn, e["pinned"], task["interface"], task["modes"])["name"]
        role = ROLE_LABELS.get(e.get("role"), "")
        gains = ", ".join(f'+{b["delta"]:.0f} {_short_board(k)} (#{b["rank"]})' for k, b in e["boards"].items())
        return [f'🆕 {task["label"]}{f" ({role})" if role else ""}', _head(c), _money_line(c),
                f'📈 dépasse {pinned} : {gains}', _why(e)]
    if task and task["interface"] == "decisions" and a["kind"] in ("new_best", "challenger"):
        return _decision_block(conn, a, task)
    if a["kind"] == "new_best":
        c = catalog.card(conn, a["subject"], task["interface"], task["modes"])
        return [f'🆕 {task["label"]} — nouveau n°1 proposé', _head(c), _money_line(c),
                f'Le router garde {e["previous_name"]} tant que tu ne valides pas.',
                (f'📈 dépasse {e["previous_name"]} : {e["score"]:.0f} vs {e["previous_score"] or 0:.0f}' if e.get("score") is not None
                 else f'🧪 version plus récente de {e["previous_name"]}, pas encore classée sur ce benchmark'), _why(e)]
    if a["kind"] == "tier":
        model_id, _, variant = a["subject"].partition("/")
        c = catalog.card(conn, model_id, "chat")
        cur = e.get("current", "")
        cur_id, _, cur_var = cur.partition("/")
        cur_name = catalog.card(conn, cur_id, "chat")["name"] + (f" ({cur_var})" if cur_var else "")
        return [f'📐 Niveau texte {e["level"]}', f'{_head(c)} ({variant})',
                f'📊 {_fr(e["score"], 1)} AA · {_fr(e["real_cost"], 3)} $/tâche',
                f'📈 remplacerait {cur_name}' + (f' ({_fr(e["current_score"], 1)} AA)' if e.get("current_score") else ""),
                _why(e)]
    if a["kind"] == "nerf":
        c = catalog.card(conn, a["subject"], task["interface"] if task else "chat")
        drops = " ; ".join(f'{_short_board(d["board"].replace(":", " "))} {d["before"]:.0f} → {d["after"]:.0f}'
                           for d in e["drops"][:3])
        return [f'📉 Dégradation — {c["name"]} ({e["active_as"]}, {task["label"] if task else a["task"]})',
                f'   {drops}', '→ le routeur réévalue au prochain cycle']
    if a["kind"] == "pareto":
        model_id, _, variant = a["subject"].partition("/")
        c = catalog.card(conn, model_id, "chat")
        return ['💸 Entre dans la frontière de Pareto (texte)', f'{_head(c)} ({variant})',
                f'📊 {_fr(e["score"], 1)} AA · {_fr(e["real_cost"], 3)} $/tâche', _why(e)]
    if a["kind"] == "board_down":
        board, _, btask = e["board"].partition(":")
        labels = [r["label"] for r in conn.execute("select label from models.tasks where task = any(%s) order by label",
                                                    (e["tasks"],))]
        last = e.get("last_ok")
        last = datetime.fromisoformat(str(last)).strftime("%d/%m") if last else "jamais"
        return [f'⚠️ Classement inaccessible : {_board_fr(f"{catalog.BOARDS.get(board, board)} {btask}")}',
                f'   {e["reason"]} — dernière lecture réussie : {last}',
                f'   Tâches touchées : {", ".join(labels)}', '   → je tente de le réparer ; le router garde le dernier choix connu']
    return [f'• {a["kind"]} {a["subject"]}']


SHORT_TASK = {"decision": "Routage d’intention", "decision_vision": "Décision avec image"}


def _decision_block(conn, a: dict, task: dict) -> list[str]:
    """Decision model proposal, short (2026-10-16: « trop gros, des informations inutiles »): who replaces
    whom, the three axes side by side, a one-line verdict. Buttons do the rest."""
    from walter_router.analysis import decision_pareto as dp
    e = a["evidence"]
    pts = dp.points(conn, task["modes"])
    by = {p["model_id"]: p for p in pts}
    new, cur = by.get(a["subject"]), by.get(e.get("previous") or e.get("pinned"))
    label = SHORT_TASK.get(a["task"], task["label"])
    if not new or not cur:
        return [f'🧭 {label} : {_name(conn, a["subject"])} proposé']

    def fr(x, d=1):
        return f"{x:.{d}f}".replace(".", ",")
    lines = [f'🧭 {label}', f'{new["name"]} proposé à la place de {cur["name"]}', "",
             f'🧠 Intelligence : {fr(new["index"])} vs {fr(cur["index"])}',
             f'⚡ Vitesse : {new["ms"]:.0f} ms vs {cur["ms"]:.0f} ms',
             f'💰 Prix : {fr(new["cost"])} $ vs {fr(cur["cost"])} $ (par million de tâches)', ""]
    from walter_router.analysis.recommend import recommendation   # written once by the router's L1 model from facts about the stack
    lines.append(f"💡 {recommendation(conn, a, new, cur)}")
    return lines


def _group_key(conn, a: dict) -> tuple:
    if a["kind"] != "challenger":
        return (a["alert_id"],)
    iface = conn.execute("select interface from models.tasks where task = %s", (a["task"],)).fetchone()
    return ("challenger", a["subject"], iface and iface["interface"])


BOARD_TASKS = {"text_to_video": "vidéo depuis texte", "image_to_video": "animation d'image", "text_to_image": "image",
               "image_edit": "retouche d'image", "tts": "voix", "music": "musique", "text": "texte",
               "text_coding": "code", "webdev": "web", "3d": "3D", "frontend": "front-end", "decision": "", "intelligence": "intelligence",
               "wer": "fidélité (100 − WER)", "speed": "vitesse", "rerank": "rerank (ELO)", "rerank_speed": "rerank latence",
               "embeddings": "embeddings (ELO)", "embeddings_speed": "embeddings latence",
               "retrieval_fr": "recherche en français"}


def _board_fr(key: str) -> str:
    """'Arena text_to_video' -> 'Arena vidéo depuis texte'."""
    source, _, task = key.rpartition(" ")
    return f"{source} {BOARD_TASKS.get(task, task.replace('_', ' '))}".strip()


def _modes_fr(modes: list[str]) -> str:
    return ", ".join(media.MODE_LABELS.get(m, m) for m in ("t2i", "i2i", "t2v", "i2v", "r2v", "v2v") if m in modes)


def _origin(e: dict) -> str | None:
    """'nouveau chez kie' -> 'Nouveau chez Kie'."""
    why = [str(w) for w in e.get("why") or []]
    if not why:
        return None
    out = "; ".join(why[:2])
    for k, v in catalog.PROVIDERS.items():
        out = out.replace(f"chez {k}", f"chez {v}")
    out = re.sub(r"nouveau sur (\w+):(\w+)", lambda m: "nouveau au classement "
                 + _board_fr(f"{catalog.BOARDS.get(m.group(1), m.group(1))} {m.group(2)}"), out)
    return out[:1].upper() + out[1:]


def _price_lines(c: dict, current: dict | None = None) -> list[str]:
    """One line per resolution with its cheapest provider, then the current model's entry price."""
    items = [(r, v) for r, v in c["prices"].items() if r] or list(c["prices"].items())
    if not items:
        return [f"💰 {catalog.price_text(c)}"]
    unit = catalog.UNIT_SHORT.get(items[0][1]["unit"] or "", "$")
    per = {"$/s": "Prix par seconde", "$/img": "Prix par image"}.get(unit, f"Prix ({unit})")
    lines = [f"💰 {per}"]
    lines += [f"• {r or 'standard'} : {catalog.money(v['price'])} $ — {catalog.PROVIDERS.get(v['provider'], v['provider'])}"
              for r, v in items[:5]]
    if c["audio"] == [False, True]:
        lines.append("  son en option")
    if current and current["prices"]:
        lo = min(v["price"] for v in current["prices"].values())
        lines.append(f"• Actuel, {current['name']} : dès {catalog.money(lo)} $")
    return lines


def _challenger_group(conn, group: list[dict]) -> list[str]:
    """One block for one new model that beats one or several of the owner's choices (2026-10-14:
    no reference numbers, one fact per line)."""
    a0 = group[0]
    task = conn.execute("select interface, modes from models.tasks where task = %s", (a0["task"],)).fetchone()
    c = catalog.card(conn, a0["subject"], task["interface"], task["modes"])
    origin = next((o for o in (_origin(a["evidence"]) for a in group) if o), None)
    lines = [f'{catalog.icon(c)} {c["name"]}', " · ".join(x for x in (origin, _modes_fr(c["modes"])) if x)]
    current, seen_tasks = None, set()
    for a in group:   # 2026-10-14: which router category, and the full comparison (won AND lost boards)
        e = a["evidence"]
        pinned = catalog.card(conn, e["pinned"], task["interface"], task["modes"])
        current = current or pinned
        label = conn.execute("select label from models.tasks where task = %s", (a["task"],)).fetchone()["label"]
        pref = conn.execute("""select label, description from models.preferences where task = %s and role = %s""",
                            (a["task"], a.get("role") or "default")).fetchone()
        role = (pref and pref["label"]) or ("" if (a.get("role") or "default") == "default"
                                            else ROLE_LABELS.get(a.get("role"), a.get("role")))
        lines += ["", f"🎯 Catégorie du router : {label} › {role}" if role else f"🎯 Catégorie du router : {label}"]
        if pref and pref["description"]:
            lines.append(f"   {pref['description']}")
        lines.append(f"   Aujourd'hui : {pinned['name']}")
        on_change = (conn.execute("select requirements from models.tasks where task = %s", (a["task"],)).fetchone()
                     ["requirements"] or {}).get("on_change")
        if on_change:   # what adopting really implies for the modules (embeddings: re-vectorise every bank)
            lines.append(f"⚠️ {on_change}")
        if a["task"] in seen_tasks:
            continue
        seen_tasks.add(a["task"])
        comp = e.get("composite") or {}
        if comp.get("challenger") is not None and comp.get("pinned") is not None:
            ranks = f" ({comp['rank']}e contre {comp['pinned_rank']}e)" if comp.get("rank") and comp.get("pinned_rank") else ""
            lines += ["", f"📊 Score global : {comp['challenger']:.0f} contre {comp['pinned']:.0f}"
                          f" pour {pinned['name']}{ranks}"]
        boards = e.get("all_boards") or {k: {"challenger": v["score"], "pinned": v["pinned_score"],
                                             "variant": v.get("variant")} for k, v in e["boards"].items()}
        for name, b in boards.items():
            if b.get("challenger") is None:
                continue
            if b.get("pinned") is None:
                lines.append(f"• {_board_fr(name)} : {b['challenger']:.0f} ({pinned['name']} non classé)")
                continue
            mark = "✔" if b["challenger"] > b["pinned"] else "✖"
            version = f" (version {b['variant']})" if b.get("variant") and b["variant"] not in ("", "default") else ""
            raw = b.get("raw")
            if raw and raw[1] is not None:   # latency / WER: the measure itself, lower = better
                d = 0 if raw[2] == "ms" else 2
                lines.append(f"• {_board_fr(name)} : {_fr(raw[0], d)} {raw[2]} contre {_fr(raw[1], d)} {raw[2]} "
                             f"{mark}{version}")
                continue
            lines.append(f"• {_board_fr(name)} : {b['challenger']:.0f} contre {b['pinned']:.0f} {mark}{version}")
    return lines + [""] + _price_lines(c, current) + _route_line(conn, a0, c)


def _route_line(conn, a: dict, c: dict) -> list[str]:
    """'🔁 Fournisseurs : Kie → OpenRouter · Secours : Wan 3' for a media model (what would run if adopted)."""
    if c["interface"] not in ("video", "image", "audio", "music"):
        return []
    from walter_router.serve import media_exec
    try:
        cfg = media_exec._models().get(a["subject"]) or {}
        mode = {"text_to_video": "t2v", "image_to_video": "i2v", "text_to_image": "t2i", "image_edit": "i2i"}.get(a["task"])
        order = media_exec.choose_provider(conn, a["subject"], c["interface"], None,
                                           bool((cfg.get("kie") or {}).get(mode)), media_exec.openrouter_id(conn, a["subject"]))
        fb = media_exec.fallback_models(conn, a["task"], a.get("role"), a["subject"], mode, n=1)
    except Exception:  # noqa: BLE001 — the line is informative only
        return []
    route = " → ".join(catalog.PROVIDERS.get(p, p) for p in order) or "aucun branché"
    return [f"🔁 Fournisseurs : {route}" + (f" · Secours : {_name(conn, fb[0])}" if fb else "")]


def render(alerts: list[dict], conn=None, typed: bool = False) -> str:
    return "\n\n━━━━━━━━━━\n\n".join(render_each(alerts, conn, typed))


def render_each(alerts: list[dict], conn=None, typed: bool = False) -> list[str]:
    """One message per piece of news (2026-10-16: « 2 messages différents, pas un gros message »)."""
    groups: dict[tuple, list[dict]] = {}
    for a in alerts:
        groups.setdefault(_group_key(conn, a), []).append(a)
    day = datetime.now(timezone.utc).strftime("%d/%m")
    out = []
    for key, group in groups.items():
        lines = _challenger_group(conn, group) if key[0] == "challenger" else _block(conn, group[0])
        if typed:
            n = group[0].get("ref") or group[0]["alert_id"]
            lines.append(f"→ « adopter {n} » ou « ignorer {n} »")
        out.append(f"W.Alter Router — {day}\n\n" + "\n".join(x for x in lines if x is not None).strip())
    return out


# Buttons (2026-10-14): one row per piece of news; the Hermes plugin walter-router handles the clicks
# (callback data 'wr:<a|d>:<ref>[:<role>]' → `walter-router verdict`).
BUTTONS = {"challenger": (("✅ Changer", "a"), ("✖️ Garder l'actuel", "d")),
           "tier": (("✅ Changer", "a"), ("✖️ Garder l'actuel", "d")),
           "new_best": (("✅ Passer au nouveau", "a"), ("✖️ Garder l'actuel", "d")),
           "pareto": (("👍 Noté", "a"), ("✖️ Ignorer", "d")),
           "nerf": (("👁️ Masquer", "d"),),
           "board_down": (("👁️ Vu", "d"),),
           "plan_change": (("✅ Mettre à jour", "a"), ("✖️ Ignorer", "d"))}


def keyboard(conn, alerts: list[dict]) -> list[list[dict]]:
    groups: dict[tuple, list[dict]] = {}
    for a in alerts:
        groups.setdefault(_group_key(conn, a), []).append(a)
    rows = []
    for group in groups.values():
        a0 = group[0]
        n = a0.get("ref") or a0["alert_id"]
        rows.append([{"text": _button_text(conn, a0, label, code), "callback_data": f"wr:{code}:{n}"}
                     for label, code in (BUTTONS.get(a0["kind"], (("✖️ Ignorer", "d"),))
                                         if (a0.get("evidence") or {}).get("action") != "none" else (("👁️ Vu", "d"),))])
        roles = sorted({a.get("role") or "" for a in group} - {""})
        if a0["kind"] == "challenger" and len(roles) > 1:   # one model beating several roles: adopt one role only
            rows.append([{"text": f"✅ Seulement {ROLE_LABELS.get(r, r)}"[:40], "callback_data": f"wr:a:{n}:{r}"[:64]}
                         for r in roles][:4])
    return rows


def _name(conn, model_id: str | None) -> str:
    if not model_id or conn is None:
        return model_id or ""
    row = conn.execute("select coalesce(display_name, model_id) as n from models.canonical where model_id = %s",
                       (model_id,)).fetchone()
    return row["n"] if row else model_id


def _button_text(conn, a: dict, label: str, code: str) -> str:
    """'✅ Passer à Grok Imagine Video 1.5' / '✖️ Garder MiniMax H3' (names, not numbers: several news per message)."""
    e = a.get("evidence") or {}
    if a["kind"] in ("challenger", "tier", "new_best"):
        if code == "a":
            return f"✅ Passer à {_name(conn, (a.get('subject') or '').partition('/')[0])}"[:48]
        cur = e.get("pinned") or e.get("previous") or (e.get("current") or "").partition("/")[0]
        return f"✖️ Garder {_name(conn, cur)}"[:48] if cur else label
    if a["kind"] == "new_best" and code == "d" and e.get("previous_name"):
        return f"↩️ Garder {e['previous_name']}"[:48]
    if a["kind"] in ("board_down", "plan_change"):
        return label
    return f"{label} · {_name(conn, (a.get('subject') or '').partition('/')[0])}".rstrip(" ·")[:48]


TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


_BOT_TOKEN: list[str] = []


def _bot_token() -> str:
    """Walter's Telegram bot (grant `telegram-bot` of walter-secrets), read once per process, never logged."""
    if not _BOT_TOKEN:
        r = subprocess.run(["walter-secret", "grant", "access", "telegram-bot"], capture_output=True, text=True,
                           timeout=120)
        if r.returncode or not r.stdout.strip():
            raise RuntimeError("Telegram bot grant unavailable (walter-secret grants telegram-bot)")
        _BOT_TOKEN.append(r.stdout.strip())
    return _BOT_TOKEN[0]


def telegram(method: str, payload: dict) -> dict:
    """Bot API call with Walter's own bot (the one the Hermes gateway also serves)."""
    from urllib.request import Request, urlopen
    token = _bot_token()
    req = Request(TELEGRAM_API.format(token=token, method=method), data=json.dumps(payload).encode(),
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=30) as resp:  # noqa: S310 (fixed host)
        out = json.loads(resp.read())
    if not out.get("ok"):
        raise RuntimeError(f"telegram {method}: {out.get('description')}")
    return out["result"]


def home_chat() -> str:
    """The owner's Telegram chat = the gateway's home channel (top-level TELEGRAM_HOME_CHANNEL in config.yaml)."""
    import re
    m = re.search(r"^TELEGRAM_HOME_CHANNEL:\s*'?(-?\d+)'?\s*$", (HERMES.parents[3] / "config.yaml").read_text(), re.M)
    chat = m.group(1) if m else instance.env_value("TELEGRAM_HOME_CHANNEL")
    if not chat:
        raise RuntimeError("no Telegram home channel")
    return chat


def send_with_buttons(text: str, rows: list[list[dict]]) -> None:
    """Through Walter's own Telegram door (lot E6, 2026-11-10: `walter-telegram send`, no longer Hermes' bot): it
    chunks at Telegram's limit, buttons on the last message; their clicks come back as `walter-router button`."""
    r = subprocess.run(["walter-telegram", "send", "--plain", "--buttons", json.dumps(rows or []), "-"], input=text,
                       capture_output=True, text=True, timeout=180)
    try:
        out = json.loads((r.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        out = {"ok": False, "error": (r.stderr or "no answer").strip()[-200:]}
    if r.returncode or not out.get("ok"):
        raise RuntimeError(f"telegram: {out.get('error')}")


def _assign_refs(conn, alerts: list[dict]) -> list[dict]:
    """Short numbers the owner can answer with (1, 2, 3…), unique among alerts still awaiting their answer."""
    used = {r["ref"] for r in conn.execute("""select ref from models.alerts where ref is not null
                                              and status = 'notified' and notified_at > now() - interval '30 days'""")}
    out, n, by_group = [], 1, {}
    for a in alerts:
        key = _group_key(conn, a)
        if key not in by_group:
            while n in used:
                n += 1
            used.add(n)
            by_group[key] = n
        conn.execute("update models.alerts set ref = %s where alert_id = %s", (by_group[key], a["alert_id"]))
        out.append({**a, "ref": by_group[key]})
    return out


def notify(conn, dry_run: bool = False) -> dict:
    alerts = pending(conn)
    if not alerts:
        return {"sent": 0}
    alerts = _assign_refs(conn, alerts)
    groups: dict[tuple, list[dict]] = {}
    for a in alerts:
        groups.setdefault(_group_key(conn, a), []).append(a)
    if dry_run:
        return {"sent": 0, "dry_run": [{"text": render_each(g, conn)[0], "buttons": keyboard(conn, g)}
                                       for g in groups.values()]}
    errors = []
    for g in groups.values():   # one Telegram message (and its buttons) per piece of news
        try:
            send_with_buttons(render_each(g, conn)[0], keyboard(conn, g))
        except Exception as exc:  # noqa: BLE001 — text-only fallback (typed answers still work)
            out = subprocess.run([str(HERMES), "send", "-t", "telegram", render_each(g, conn, typed=True)[0]],
                                 capture_output=True, text=True, timeout=120)
            if out.returncode != 0:
                errors.append(f"buttons: {exc}; text: {(out.stderr or out.stdout)[-200:]}")
    if errors and len(errors) == len(groups):
        return {"sent": 0, "error": "; ".join(errors)}
    ids = [a["alert_id"] for a in alerts]
    conn.execute("update models.alerts set status = 'notified', notified_at = now() where alert_id = any(%s)", (ids,))
    return {"sent": len(ids)}
