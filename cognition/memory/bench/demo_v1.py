"""Memory V1 demonstrations on the REAL memory (2026-11-03), read-only: what a real runtime receives and does.

DSH headless turns (a bench workspace: never ingested into core.events; its run is a production `test` run) asked
through their real hook against the production gateway, with a control run without memory. Personal contents
(people, places) are written only to the instance's own report file (local), the console gets checks and counts.

  walter-python bench/demo_v1.py decision|context|kardex|all [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("WALTER_MEMORY_DATABASE_URL", "postgresql://hindsight@127.0.0.1:5433/hindsight")
import e2e_v1 as e2e  # noqa: E402 — the same DSH harness (the test-DSN guard only protects e2e's writers)
from walter_memory.db import connection  # noqa: E402


def injected_prod(prompt: str) -> dict:
    import httpx
    from walter_memory import client
    r = httpx.post("http://127.0.0.1:8890/v1/context", headers={"Authorization": f"Bearer {client.token()}"}, timeout=30,
                   json={"query": prompt, "budget": {"profile": 0, "people": 300, "knowledge": 600, "evidence": 300},
                         "include_profile": False, "caller": "dsh-hook", "mode": "on", "session_id": None})
    r.raise_for_status()
    return r.json()


def tool_calls(session: str | None) -> list[dict]:
    if not session:
        return []
    for _ in range(20):                       # walter-logs-watch syncs the DSH session within seconds
        with connection() as conn:
            rows = conn.execute("""select e.tool, left(e.text, 300) args from walter_logs.events e
                                   join walter_logs.sessions s on s.session_id = e.session_id
                                   where s.native_id like %s and e.type = 'tool/call' order by e.seq""",
                                (f"%{session.removeprefix('session-')}%",)).fetchall()
        if rows:
            return rows
        time.sleep(3)
    return []


def case_decision() -> dict:
    """A decision changed in THIS Claude Code conversation (03/11: no more long shadow phases, integrate P1 end to
    end) is found by DSH, another runtime, in a new session, without tools."""
    q = ("Sans utiliser aucun outil, réponds en deux phrases : pour livrer la Memory V1, Monsieur veut-il encore de "
         "longues périodes en mode fantôme avant d'activer ? Qu'a-t-il décidé le 3 novembre ?")
    ctx = injected_prod(q)
    on, off = e2e.ask_dsh(q, production=True), e2e.ask_dsh(q, memory=False, production=True)
    with connection() as conn:
        old = conn.execute("""select status from core.derived_items where generation = 'g1'
                              and content = 'P1.1 doit rester en mode fantôme pendant l’observation en production.'""").fetchone()
    checks = {"old_rule_superseded": bool(old) and old["status"] == "superseded",
              "injected": e2e.has(ctx["text"], "fantôme", "shadow") and e2e.has(ctx["text"], "intégration", "tests isolés"),
              "model_used_it": e2e.has(on["answer"], "non") and e2e.has(on["answer"], "intégr", "activ", "tests"),
              "control_does_not_know": not e2e.has(off["answer"], "intégration complète")}
    return {"case": "decision", "injected_tokens": ctx["trace"]["total_tokens"], "injected": ctx["text"],
            "with_memory": on, "control_without_memory": off, "checks": checks, "pass": all(checks.values())}


def case_context() -> dict:
    """A short context, then the model looks for the details itself: DSH with its Walter tools (MCP), asked a
    question whose full answer is in a period view."""
    q = ("Quelles décisions Monsieur a-t-il validées sur Walter Memory le 2 novembre 2026 ? Donne-les avec leurs "
         "identifiants ; si le contexte injecté ne suffit pas, ouvre la vue de la journée avec memory_view.")
    ctx = injected_prod(q)
    on = e2e.ask_dsh(q, production=True, timeout=420)
    calls = tool_calls(on.get("session"))
    used_view = [c for c in calls if "memory_view" in (c["tool"] or "")]
    checks = {"context_short": ctx["trace"]["total_tokens"] <= 2500,
              "context_points_to_views": "period:" in ctx["text"] or "g1:subject" in ctx["text"],
              "model_opened_a_view": bool(used_view),
              "answer_cites_ids": sum(1 for w in (on["answer"] or "").replace("[", " ").replace("]", " ").split()
                                      if len(w.strip("`(),.;:")) == 8 and all(ch in "0123456789abcdef" for ch in w.strip("`(),.;:"))) >= 2}
    return {"case": "context", "injected_tokens": ctx["trace"]["total_tokens"], "injected": ctx["text"],
            "tool_calls": calls, "with_memory": on, "checks": checks, "pass": all(checks.values())}


def case_kardex() -> dict:
    """A contact's card: what the cloud model may see (claims within policy, metrics) — and nothing of the owner's
    private life; a message drafted for that contact that would leak it is stopped. Contents go to the local report."""
    from walter_memory import disclosure, kardex_enrich, read_policy, social
    eid = kardex_enrich.top_contacts(1)[0]
    cloud = social.person_card(eid, "cloud_allowed")
    third = social.person_card(eid, "local_only", audience="third_party")
    with connection() as conn:
        claims_all = conn.execute("""select c.claim, c.sensitivity, c.mention_policy, c.status from kardex.claims c
                                     join core.entities e on e.kardex_contact_id = c.contact_id where e.entity_id = %s""",
                                  (eid,)).fetchall()
        home = conn.execute("""select canonical_name from core.entities where entity_type = 'place'
                               and attributes ? 'home'""").fetchone()
        mine = conn.execute("""select content from core.derived_items where generation = 'g1' and status = 'derived'
                               and kind in ('visit', 'appointment') order by valid_from desc limit 20""").fetchall()
    shown = [c["claim"] for c in (cloud.get("kardex") or {}).get("claims") or []]
    withheld = [c for c in claims_all if c["claim"] not in shown]
    card_text = json.dumps(cloud, default=str, ensure_ascii=False)
    owner_private_in_card = [m["content"][:40] for m in mine if m["content"][:40] in card_text] + \
        ([home["canonical_name"]] if home and home["canonical_name"] in card_text else [])
    name = cloud["entity"]["canonical_name"]
    draft_home = f"Salut {name}, passe me voir à {home['canonical_name']} ce soir" if home else ""
    leak = disclosure.check(draft_home, to=None, channel="demo", model=False) if draft_home else None
    promise = disclosure.check(f"Salut {name}, ok pour samedi 20h, je t'avance les 2000 bahts", to=None, channel="demo",
                               model=False)
    checks = {"card_has_contact_knowledge": len(shown) >= 1,
              "policy_withheld_some": len(withheld) >= 1 and all(c["mention_policy"] != "never_reference" for c in
                                                                 claims_all if c["claim"] in shown),
              "no_owner_private_info_in_card": not owner_private_in_card,
              "third_party_audience_sees_less": len((third.get("kardex") or {}).get("claims") or []) <= len(shown),
              "home_place_blocked_in_message": (leak or {}).get("action") == "block",
              "commitment_needs_approval": promise["action"] == "ask"}
    report = {"contact": name, "cloud_card_claims": shown, "withheld": [dict(c) for c in withheld],
              "third_party_claims": (third.get("kardex") or {}).get("claims"), "metrics": cloud.get("relationship"),
              "draft_checks": {"home": leak, "promise": promise}}
    return {"case": "kardex", "counts": {"claims_total": len(claims_all), "shown_to_cloud": len(shown),
                                         "withheld": len(withheld)},
            "local_report": report, "checks": checks, "pass": all(checks.values())}


def case_everything() -> dict:
    """« Oui tout » (2026-11-03): the cloud model really uses messaging and GPS knowledge. DSH (cloud model, no tools)
    is asked about the most active contact and about yesterday evening's whereabouts; checks compare its answers with
    what Memory holds (claims, place names) — contents go to the local report only."""
    from walter_memory import kardex_enrich, social
    from walter_memory.flows import tz
    from datetime import timedelta
    eid = kardex_enrich.top_contacts(1)[0]
    card = social.person_card(eid, "cloud_allowed")
    name = card["entity"]["canonical_name"]
    claims = [c["claim"] for c in (card.get("kardex") or {}).get("claims") or []]
    words = {w.lower().strip(".,;:!?«»()") for c in claims for w in c.split() if len(w) >= 6} - {name.lower()}
    q1 = f"Sans utiliser aucun outil, réponds en trois phrases : que sais-tu de {name} et de nos derniers échanges ?"
    on1, off1 = e2e.ask_dsh(q1, production=True), e2e.ask_dsh(q1, memory=False, production=True)
    z = tz()
    with connection() as conn:
        places = [r["canonical_name"] for r in conn.execute(
            "select canonical_name from core.entities where entity_type = 'place' and status = 'active'")]
    q2 = "Sans utiliser aucun outil, réponds en une phrase : où étais-je ces derniers jours, d'après mes positions GPS ?"
    on2 = e2e.ask_dsh(q2, production=True)
    hits1 = sorted(w for w in words if w in (on1["answer"] or "").lower())
    hit2 = [p for p in places if p and p.lower() in (on2["answer"] or "").lower()]
    checks = {"contact_knowledge_used": len(hits1) >= 2, "control_does_not_know": len(
                  [w for w in words if w in (off1["answer"] or "").lower()]) < len(hits1),
              "gps_places_used": bool(hit2)}
    report = {"contact": name, "answer_contact": on1, "control": off1, "answer_places": on2, "claim_words_hit": hits1,
              "places_hit": hit2}
    return {"case": "everything", "counts": {"claim_words_hit": len(hits1), "places_hit": len(hit2),
                                             "answer_chars": [len(on1["answer"] or ""), len(on2["answer"] or "")]},
            "local_report": report, "checks": checks, "pass": all(checks.values())}


CASES = {"decision": case_decision, "context": case_context, "kardex": case_kardex, "everything": case_everything}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("case", choices=[*CASES, "all"])
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    results = [CASES[c]() for c in (CASES if a.case == "all" else [a.case])]
    if a.out:
        Path(a.out).mkdir(parents=True, exist_ok=True)
        p = Path(a.out) / f"demo-{a.case}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
        p.write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str))
        p.chmod(0o600)
    for r in results:
        print(r["case"], "PASS" if r["pass"] else "FAIL", json.dumps(r["checks"]), json.dumps(r.get("counts", {})))
        if r["case"] not in ("kardex", "everything"):
            for k in ("with_memory", "control_without_memory"):
                if k in r:
                    print(f"  {k}: {r[k]['answer']!r} ({r[k]['seconds']} s)")
            print("  injected tokens:", r.get("injected_tokens"), " tool calls:", [c["tool"] for c in r.get("tool_calls", [])])


if __name__ == "__main__":
    main()
