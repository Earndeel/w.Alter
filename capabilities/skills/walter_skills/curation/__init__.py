"""Curation — keeps the library small, clean and findable, through small operators sharing one contract
(operators.py), checks every rewrite must pass (base.validate) and one run per night:

  shadow (until curation.shadow_until): everything happens on git branch curator/<date>, master untouched
  active: commits on master, each with its evidence in skills.ledger
"""
from __future__ import annotations

import json
from collections import defaultdict

from .. import config, postes, registry, store
from ..ranker import Encoder
from ..retrieval import aliases
from . import base, signals
from .operators import OPERATORS

REPORTS = store.ROOT / "reports"


def run(apply: bool | None = None, use_models: bool = True, only: set[str] | None = None) -> dict:
    cfg = config.get("curation")
    day = signals.now().strftime("%Y-%m-%d")
    mode = base.mode_today(cfg, day, apply)
    root = store.ROOT if mode == "active" else base.worktree(day)
    ctx = base.Context(root=root, mode=mode, day=day, cfg=cfg, cards=registry.cards(), aliases=aliases(),
                       use_models=use_models and postes.available("judge"))
    active = list(store.iter_skills(root=root))
    ctx.sig = {"active": active, "usage": signals.usage(ctx.aliases), "needed": signals.judged_needed(),
               "pins": signals.pinned(), "cool": signals.recently_curated(cfg["cooldown_days"]),
               "successors": signals.successors(), "sim": signals.similarity(active, ctx.cards, Encoder.get())}
    editor_ok = use_models and postes.available("editor")
    proposed, done = {}, defaultdict(list)
    for op in OPERATORS:
        if only and op.name not in only:
            continue
        props = op.propose(ctx)
        proposed[op.name] = props
        if op.editor and not editor_ok:
            continue
        for p in props[:cfg[op.limit]] if op.limit else props:
            try:
                r = op.apply(ctx, p)
            except Exception as e:  # one failing proposal never stops the run
                r = {"status": "error", "error": f"{type(e).__name__}: {str(e)[:200]}"}
            done[f"{op.name}:{r.get('status')}"].append(p | r)
    summary = {"mode": mode, "editor": "ok" if editor_ok else "unavailable",
               "proposed": {k: len(v) for k, v in proposed.items()}, "done": {k: len(v) for k, v in done.items()}}
    _report(day, mode, root, proposed, done, summary)
    registry.ledger("curator" if mode == "active" else "curator.shadow", "run", None, None, summary)
    return {"summary": summary, "branch": None if mode == "active" else f"curator/{day}"}


def _report(day: str, mode: str, root, proposed: dict, done: dict, summary: dict) -> None:
    REPORTS.mkdir(exist_ok=True)
    lines = [f"# walter-skills curation — {day} ({mode})", "",
             f"Changes on git branch `curator/{day}` (master untouched)." if mode == "shadow"
             else "Changes committed on master (skills.ledger has the evidence).", "", "| | proposed | |", "|---|---|---|"]
    for k, v in summary["proposed"].items():
        res = ", ".join(f"{d.split(':')[1]} {n}" for d, n in summary["done"].items() if d.startswith(k + ":"))
        lines.append(f"| {k} | {v} | {res} |")
    for k, items in list(done.items()) + [(f"proposed {k}", v) for k, v in proposed.items()]:
        lines += ["", f"## {k} ({len(items)})", ""]
        lines += [f"- {json.dumps(x, ensure_ascii=False, default=str)[:500]}" for x in items[:60]] or ["- none"]
    (REPORTS / f"curation-{day}.md").write_text("\n".join(lines) + "\n")


def digest(days: int = 7) -> str:
    """Weekly Telegram digest (short, French)."""
    with registry.db() as c:
        rows = c.execute("""select action, count(*) n from skills.ledger where actor in ('curator', 'learning')
                            and at > now() - make_interval(days => %s) group by 1 order by 2 desc""", (days,)).fetchall()
        last = c.execute("""select evidence from skills.ledger where actor = 'curator.shadow' and action = 'run'
                            order by at desc limit 1""").fetchone()
    parts = [f"Skills W.Alter — semaine : {sum(1 for _ in store.iter_skills())} actifs."]
    if rows:
        parts.append("Appliqué : " + ", ".join(f"{r['n']} {r['action']}" for r in rows) + ".")
    if last:
        parts.append(f"Fantôme (branche, rien appliqué) : {last['evidence'].get('done', {})}.")
    return " ".join(parts)
