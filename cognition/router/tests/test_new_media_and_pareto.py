"""2026-11-20 (owner: « les models d'image n'ont pas été mis à jour, le pareto des models general non plus ») —
token-billed image models get a comparable price, OpenRouter makes a media model runnable without a hand-listed
executor, and the official-price chart has its own Pareto frontier."""
from walter_router.analysis import select as sel
from walter_router.interface import page
from walter_router.serve import media_exec


def _offer(provider, pricing=None, norm_price=None, modes=("t2i", "i2i")):
    return {"provider": provider, "interface": "image", "offer_key": f"{provider}/x", "access": "paid",
            "offer_kind": "generation", "modes": list(modes), "resolution": None, "norm_price": norm_price,
            "norm_unit": "per image" if norm_price is not None else None, "pricing": pricing or {}}


def test_token_billed_openrouter_offer_is_priced_at_aa_list_price():
    offers = [_offer("openrouter", {"image_output": "0.00003", "prompt": "0.000008"})]
    assert sel.media_route(offers, "image", ["t2i"])["paid"]["cost"] is None          # no reference: unknown, as before
    paid = sel.media_route(offers, "image", ["t2i"], list_cost=0.21)["paid"]
    assert paid["cost"] == 0.21 and paid["provider"] == "openrouter"


def test_per_image_offer_wins_when_cheaper_than_list_price():
    offers = [_offer("openrouter", {"image_output": "0.00003"}), _offer("kie", norm_price=0.03)]
    assert sel.media_route(offers, "image", ["t2i"], list_cost=0.21)["paid"]["provider"] == "kie"


def test_unpriced_offer_is_not_given_the_list_price():
    assert sel.media_route([_offer("openrouter", {})], "image", ["t2i"], list_cost=0.21)["paid"]["cost"] is None


def test_derived_executor_runs_only_its_openrouter_modes():
    derived = {"kind": "image", "openrouter": "x/y", "derived": True, "modes": ["t2i"]}
    assert media_exec.supports(derived, ["t2i"]) and not media_exec.supports(derived, ["i2i"])
    assert media_exec.supports({"kind": "image", "kie": {"i2i": "p"}}, ["i2i"])     # configured: its own paths


def test_derived_executors_include_openrouter_image_models():
    from walter_router.store import db
    with db.connect() as conn:
        if "openrouter" not in sel.latest_snapshots(conn):
            return
        models = media_exec._models(conn)
        configured = media_exec._models()
        assert set(configured) <= set(models)
        assert all(models[m] == configured[m] for m in configured)            # a configured executor is never replaced
        assert any(c.get("derived") and c["kind"] == "image" for c in models.values())


def test_official_price_chart_has_its_own_frontier():
    pts = [{"model_id": "sub", "variant": "", "name": "Sub", "score": 50, "cost": 0.05, "cost_aa": 5.0},
           {"model_id": "api", "variant": "", "name": "Api", "score": 45, "cost": 0.5, "cost_aa": 0.5},
           {"model_id": "top", "variant": "", "name": "Top", "score": 60, "cost": 1.0, "cost_aa": 1.0}]
    f = page.aa_frontier(pts)
    costs = [p["cost_aa"] for p in f]
    assert costs == sorted(costs) and [p["model_id"] for p in f] == ["api", "top"]   # 'sub' is dominated at list price
    scores = [p["score"] for p in f]
    assert scores == sorted(scores)
