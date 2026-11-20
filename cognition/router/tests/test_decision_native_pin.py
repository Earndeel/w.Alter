"""2026-11-20 (owner: « le modèle de décision c'est censé être D1.2 Ultra via l'API de Liquid par défaut ») — a decision
pin on Liquid's own API heads the chain, its OpenRouter resale next, then the declared failover, then the free one."""
import json

from walter_router.serve import intent


class _Conn:
    def __init__(self, pin, resale):
        self.pin, self.resale, self.q = pin, resale, None

    def execute(self, sql, args=None):
        self.q = sql
        return self

    def fetchone(self):
        if "pinned_provider = 'liquidai'" in self.q:
            return self.pin
        if "liquid/%%" in self.q:
            return self.resale
        raise AssertionError("catalogued-offer path must not run for a Liquid pin")


def _knowledge(tmp_path, monkeypatch, decision):
    k = tmp_path / "knowledge.json"
    k.write_text(json.dumps({"decision": decision}))
    monkeypatch.setattr(intent, "KNOWLEDGE", k)


def test_liquid_pin_heads_the_chain_then_resale_failover_free(tmp_path, monkeypatch):
    _knowledge(tmp_path, monkeypatch, {"order": "best_first", "failover": ["nace/drex-max-v1.1"]})
    conn = _Conn({"pinned_model_id": "d1-2-ultra"}, {"offer_key": "liquid/d1.2-ultra"})
    assert intent.chain(conn) == ("liquidai/d1.2-ultra", "liquid/d1.2-ultra", "nace/drex-max-v1.1", "cloudflare/clef")


def test_liquid_pin_without_resale_still_goes_first(tmp_path, monkeypatch):
    _knowledge(tmp_path, monkeypatch, {"order": "best_first"})
    assert intent.chain(_Conn({"pinned_model_id": "d1.2-ultra"}, None)) == ("liquidai/d1.2-ultra", "cloudflare/clef")


def test_auto_adopt_skips_a_challenger_walter_cannot_call(monkeypatch):
    """2026-11-20: opening the svg padlock adopted Arrow 2 Telos, which no provider offers."""
    from walter_router.analysis import alerts
    from walter_router.serve import choose
    pref = {"task": "svg", "role": "default", "pinned_model_id": "old", "pinned_variant": "", "label": "SVG",
            "interface": "chat", "modes": None}
    cands = [{"alert_id": 1, "subject": "ghost", "evidence": {"composite": {"challenger": 90}}},
             {"alert_id": 2, "subject": "real", "evidence": {"composite": {"challenger": 80}}}]

    class C:
        def execute(self, sql, args=None):
            self.sql = sql
            return self

        def fetchall(self):
            return [pref] if "from models.preferences" in self.sql else cands

    adopted = []
    monkeypatch.setattr(choose, "routes_for", lambda conn, m, i, modes=None: {"callable": m == "real"})
    monkeypatch.setattr(alerts, "verdict", lambda conn, aid, *a, **k: adopted.append(aid))
    done = alerts.auto_adopt(C())
    assert adopted == [2] and done[0]["to"] == "real"
