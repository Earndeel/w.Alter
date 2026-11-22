"""2026-11-22 (owner): a challenger is judged against what its poste really uses, from counts only."""
import ast
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from walter_router.analysis import needs
from walter_router.store import db


def _gateway_funcs():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "llm" / "gateway.py").read_text())
    ns = {"Counter": Counter}
    code = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("request_needs", "decision_needs")]
    exec(compile(ast.Module(body=code, type_ignores=[]), "gateway", "exec"), ns)
    return ns["request_needs"], ns["decision_needs"]


def test_the_gateway_counts_what_a_call_asks_and_copies_nothing():
    req, dec = _gateway_funcs()
    got = req({"messages": [{"role": "user", "content": [{"type": "text", "text": "SECRET"},
                                                         {"type": "image_url", "image_url": {"url": "data:SECRET"}}]}],
               "tools": [{}, {}], "response_format": {"type": "json_schema"}, "n": 2})
    assert got == {"image_url": 1, "tools": 2, "format": "json_schema", "n": 2}
    assert "SECRET" not in json.dumps(got) and req({"messages": [{"role": "user", "content": "hi"}]}) == {}
    got = dec({"state": {"x": "SECRET"}, "media": [{"type": "image", "data": "SECRET"}], "samples": 3,
               "questions": {"a": {"type": "choice", "multiple": True}, "b": {"type": "noul"}}})
    assert got == {"image": 1, "kinds": {"multiple": 1, "noul": 1}, "n": 3} and "SECRET" not in json.dumps(got)


def test_observed_needs_per_poste():
    now = datetime.now(timezone.utc).isoformat()
    rows = [{"at": now, "task": "general/L2", "provider": "codex", "ok": True, "usage": {"in": 1000, "out": 50},
             "needs": {"image_url": 1, "tools": 3}},
            {"at": now, "task": "general/L2", "provider": "codex", "ok": True, "usage": {"in": 5000, "out": 10},
             "needs": {"tools": 3, "format": "json_object"}},
            {"at": now, "task": "general/L2", "provider": "codex", "ok": False, "usage": {"in": 99999}},
            {"at": now, "task": "decision", "provider": "liquid", "ok": True, "needs": {"image": 1, "kinds": {"multiple": 1}}},
            {"at": now, "event": "selection", "task": "general/L2"}]
    out = needs.observed(lines=[b"skip"] and [json.dumps(r).encode() for r in rows])
    g = out[("general", "L2")]
    assert g["calls"] == 2 and g["inputs"] == {"image": 0.5} and g["tools_share"] == 1.0 and g["json_share"] == 0.5
    assert g["input_tokens_max"] == 5000 and g["output_tokens_max"] == 50
    assert out[("decision", "")]["inputs"] == {"image": 1.0} and out[("decision", "")]["kinds"] == ["multiple"]


def test_a_challenger_that_cannot_do_what_the_poste_uses_loses_it():
    with db.connect() as conn:
        conn.execute("""insert into models.poste_needs (task, level, calls, window_days, inputs, tools_share, json_share,
                        max_n, input_tokens_max, output_tokens_max) values
                        ('test-poste', '', 10, 14, '{"image": 0.4}', 0.5, 0, 1, 50000, 2000)""")
        conn.execute("""insert into models.model_details (model_id, context_length, max_output_tokens, input_modalities,
                        parameters) values ('test-new', 32000, 8000, '{text}', '{tools}'),
                                           ('test-old', 128000, 8000, '{text,image}', '{tools}')""")
        c = needs.compare(conn, "test-poste", "test-new", "test-old")
        conn.rollback()
    assert "lit image" in c["lost"] and any(x.startswith("contexte") for x in c["lost"])
    assert "outils (50% des appels)" in c["kept"] and c["only_current"] == ["lit les images"]
