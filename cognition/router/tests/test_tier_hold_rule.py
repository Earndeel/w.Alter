"""2026-11-20 (owner): « il peut faire une estimation subscription basée sur le modèle précédent, si le prix api officiel
est identique. le L1 doit rester plus ou moins le même prix, mais évidemment jamais descendre en score. pareil pour L2.
et faut faire attention au changement que Artificial Analysis fait sur son index … ça recalcule les valeurs souvent à
la baisse »."""
from walter_router.analysis import alerts, changes, select as sel, tiers


# --- subscription cost price estimated from the predecessor ---------------------------------------------------------

def _offer(provider, access, pin=None, pout=None):
    return {"provider": provider, "access": access, "interface": "chat", "price_in_1m": pin, "price_out_1m": pout}


def test_new_version_at_the_same_api_price_takes_its_predecessors_ratio():
    measured = {("codex", "gpt-6-1-sol"): {"ratio": 0.1, "cost_per_1m": 1.0, "source": "modeldial"},
                ("codex", "gpt-6-astra"): {"ratio": 0.2, "source": "modeldial"}}
    offers = {"gpt-6-1-sol": [_offer("openrouter", "paid", 2, 10), _offer("codex", "subscription")],
              "gpt-6-2-sol": [_offer("openrouter", "paid", 2, 10), _offer("codex", "subscription")],
              "gpt-6-astra": [_offer("openrouter", "paid", 10, 50), _offer("codex", "subscription")],
              "gpt-6-2-astra": [_offer("openrouter", "paid", 8, 40), _offer("codex", "subscription")]}
    est = sel.estimate_from_predecessor(measured, offers)
    assert est == {("codex", "gpt-6-2-sol"): {"ratio": 0.1, "cost_per_1m": 1.0, "source": "estimated",
                                               "estimated_from": "gpt-6-1-sol"}}   # Astra: other API price, none


def test_a_measured_ratio_is_never_replaced_by_an_estimate():
    measured = {("codex", "gpt-6-1-sol"): {"ratio": 0.1}, ("codex", "gpt-6-2-sol"): {"ratio": 0.3}}
    offers = {m: [_offer("openrouter", "paid", 2, 10), _offer("codex", "subscription")]
              for m in ("gpt-6-1-sol", "gpt-6-2-sol")}
    assert sel.estimate_from_predecessor(measured, offers) == {}


# --- hold rule: same price, never a lower score ----------------------------------------------------------------------

def _c(mid, variant, score, cost, sub=None):
    route = {"paid": {"provider": "kie", "offer_key": f"kie/{mid}", "cost": cost * 3 if sub else cost},
             "subscription": None,
             "subscription_cost": {"provider": sub, "sub_id": sub, "cost": cost, "ratio": 0.1} if sub else None}
    return {"model_id": mid, "variant": variant, "display_name": f"{mid} {variant}", "score": score,
            "score_unit": "AA", "real_cost": cost, "real_cost_unit": "$/task", "route": route}


BASE = [_c("terra", "medium", 38.2, 0.0166, "codex"), _c("sol", "low", 40.6, 0.018, "codex"),
        _c("sol", "medium", 52.7, 0.040, "codex"), _c("sol", "high", 54.9, 0.0556, "codex"),
        _c("opus", "xhigh", 57.4, 0.1027, "claude-pro"), _c("opus", "max", 59.1, 0.17, "claude-pro"),
        _c("astra", "xhigh", 61.6, 0.249, "codex")]
PINS = {"L1": ("sol", "low"), "L2": ("sol", "medium"), "L3": ("opus", "xhigh")}


def _tiers(cands, pins=PINS):
    return {r["level"]: r for r in sel._tier_rows(cands, pins) if r["level"] in ("L1", "L2", "L3")}


def test_declared_tiers_stay_when_nothing_scores_better_at_their_price():
    rows = _tiers(BASE)
    assert (rows["L1"]["model_id"], rows["L1"]["variant"]) == ("sol", "low")      # never Terra medium (38.2)
    assert (rows["L2"]["model_id"], rows["L2"]["variant"]) == ("sol", "medium")
    assert rows["L1"]["reasons"]["hold"]["gain"] == 0


def test_l1_moves_to_a_better_model_at_about_the_same_price():
    cands = BASE + [_c("nova", "low", 42.0, 0.021, "codex"),       # +17 % : in the band
                    _c("luna", "max", 44.0, 0.030, "codex")]       # +67 % : too dear for L1
    l1 = _tiers(cands)["L1"]
    assert l1["model_id"] == "nova" and l1["reasons"]["hold"]["gain"] == 1.4
    ev = alerts._hold_why(l1["reasons"]["hold"], l1["reasons"].get("quota_rule"))
    assert ev and "même prix que sol/low" in ev[0]


def test_l2_never_moves_onto_l3s_subscription():
    cands = BASE + [_c("opus", "low", 54.0, 0.042, "claude-pro"), _c("sol2", "medium", 53.5, 0.045, "codex")]
    l2 = _tiers(cands)["L2"]
    assert l2["model_id"] == "sol2"


def test_l3_never_proposed_below_the_declared_score(monkeypatch):
    low = _c("cheap", "high", 55.0, 0.05, "codex")
    monkeypatch.setattr(tiers, "compute", lambda pts: {"frontier": [], "L1": None, "L2": None,
                                                       "L3": {**low, "cost": low["real_cost"]}, "params": {}})
    monkeypatch.setattr(tiers, "quota_levels", lambda *a, **k: {"L2": None, "L3": None})
    l3 = _tiers(BASE + [low])["L3"]
    assert l3["model_id"] == "opus" and l3["reasons"]["method_pick"] == "cheap/high"


def test_a_declared_tier_missing_from_the_index_falls_back_to_the_method_and_says_so():
    rows = _tiers(BASE, {**PINS, "L1": ("gone", "low")})
    assert rows["L1"]["reasons"]["declared_missing"] == "gone/low"


def test_hold_price_band():
    a = {"score": 40.0, "cost": 0.02}
    assert tiers.hold_price([{"score": 41, "cost": 0.0251}], a) is None          # 25.5 % dearer
    assert tiers.hold_price([{"score": 40.3, "cost": 0.02}], a) is None          # below the minimum gain
    assert tiers.hold_price([{"score": 41, "cost": 0.025}, {"score": 41, "cost": 0.01}], a)["cost"] == 0.01


# --- AA silent recalculation -----------------------------------------------------------------------------------------

def _rows(scores, board=("aa_intelligence", "intelligence")):
    return [{"benchmark": board[0], "task": board[1], "external_key": f"m{i}", "model_id": f"m{i}", "score": s}
            for i, s in enumerate(scores)]


def test_a_board_wide_drop_without_a_new_label_is_a_rebase_not_a_nerf_of_everyone():
    old = {("aa_intelligence", "intelligence", f"m{i}"): 50.0 + i for i in range(12)}
    new = _rows([50.0 + i - 4 for i in range(12)])
    out = changes.recalculated_boards(old, new, {})
    board = out["aa_intelligence:intelligence"]
    assert board["silent"] and board["median_shift"] == -4.0 and board["models"] == 12
    assert "sans changer de version" in changes.rebased_intelligence({"rebased": out})[0]


def test_a_few_real_nerfs_stay_nerfs():
    old = {("aa_intelligence", "intelligence", f"m{i}"): 50.0 + i for i in range(12)}
    new = _rows([50.0 + i - (4 if i < 3 else 0) for i in range(12)])
    assert changes.recalculated_boards(old, new, {}) == {}


def test_a_labelled_rebase_is_not_counted_twice():
    old = {("aa_intelligence", "intelligence", f"m{i}"): 50.0 for i in range(12)}
    assert changes.recalculated_boards(old, _rows([45.0] * 12), {"aa_intelligence:intelligence": {}}) == {}
