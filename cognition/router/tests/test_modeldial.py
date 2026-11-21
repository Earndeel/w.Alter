"""ModelDial: measured subscription quota per plan x model -> cost price of a token (owner, 2026-11-16)."""
from __future__ import annotations

import pytest

from walter_router.analysis import select as sel
from walter_router.plan import modeldial

# one row of the rendered table, as served on 2026-11-16 (class names shortened, structure unchanged)
PAGE = """<script type="application/ld+json">{"dateModified":"2026-11-05"}</script><table><tbody>
<tr><th scope="row">Opus 5.5</th>
<td><a class="m__quotaCell" href="?calc=work&amp;calc_row=claude-pro-opus-5.5-20261005&amp;period=week" title="x">
<span class="m__quotaNumber"><small>≈</small>6.69</span><span class="m__apiValue">API 等值<!-- --> <!-- -->≈ $272</span>
<span class="v__value">每 $1 ≈ 14,500 万 Token</span></a></td>
<td><a class="m__quotaCell" href="?calc=work&amp;calc_row=claude-max-5x-opus-5.5-20261005&amp;period=week" title="x">
<span class="m__quotaNumber"><small>≈</small>32.31</span><span class="m__apiValue">API 等值 ≈ $1,321</span></a></td></tr>
<tr><th scope="row"><a href="/subscriptions?plan_model=gemini-4-hydrogen">Gemini 4 Hydrogen</a></th>
<td><a class="m__quotaCell" href="?calc=work&amp;calc_row=google-pro-hydrogen-20261113" title="x">
<span class="m__quotaNumber"><small>≈</small>1.46</span><span class="v__value">每 $1 ≈ 3,154 万 Token</span></a></td></tr>
<tr><th scope="row">GPT-6.1 Sol</th>
<td><a class="m__quotaCell" href="?calc=work&amp;calc_row=openai-plus-gpt-6.1-sol" title="x">
<span class="m__quotaNumber">2.38</span><span class="m__apiValue">API 等值 ≈ $47</span></a></td>
<td><a class="m__quotaCell" href="?calc=work&amp;calc_row=openai-pro-100-gpt-6.1-sol" title="x">
<span class="m__quotaNumber">35.03</span><span class="m__apiValue">API 等值 ≈ $690</span></a></td></tr>
</tbody></table>"""


def test_parse_reads_tokens_value_and_measurement_date():
    cells = {c["row_id"]: c for c in modeldial.parse(PAGE)}
    opus = cells["claude-pro-opus-5.5-20261005"]
    assert opus["model_name"] == "Opus 5.5"
    assert opus["weekly_tokens"] == pytest.approx(6.69e8) and opus["weekly_api_usd"] == 272
    assert opus["measured"] == "2026-10-05"
    assert cells["claude-max-5x-opus-5.5-20261005"]["weekly_api_usd"] == 1321      # thousands separator
    assert cells["google-pro-hydrogen-20261113"]["weekly_api_usd"] is None         # tokens only, no API value
    assert cells["openai-plus-gpt-6.1-sol"]["measured"] == "2026-11-05"            # no date in the id: page date


def test_plan_key_never_takes_a_longer_plans_cells():
    cells = modeldial.parse(PAGE)
    assert [c["row_id"] for c in modeldial.cells_for(cells, "claude-pro")] == ["claude-pro-opus-5.5-20261005"]
    assert [c["row_id"] for c in modeldial.cells_for(cells, "openai-pro")] == []   # not « openai-pro-100-… »
    assert [c["row_id"] for c in modeldial.cells_for(cells, "openai-pro-100")] == ["openai-pro-100-gpt-6.1-sol"]


def test_model_names_link_only_on_an_exact_router_id():
    known = {"claude-opus-5-5", "gemini-4-hydrogen", "gpt-6-1-sol"}
    assert modeldial.model_id("Opus 5.5", "claude-pro", known) == "claude-opus-5-5"        # vendor word added
    assert modeldial.model_id("Gemini 4 Hydrogen", "google-pro", known) == "gemini-4-hydrogen"
    assert modeldial.model_id("GPT-6.1 Sol", "openai-plus", known) == "gpt-6-1-sol"
    assert modeldial.model_id("Sonnet 5.5", "claude-pro", known) is None                   # never guessed


def _offer(provider, access="paid", pin=None, pout=None, model_id="claude-opus-5-5"):
    return dict(provider=provider, offer_key=f"{provider}-x", access=access, interface="chat", model_id=model_id,
                price_in_1m=pin, price_out_1m=pout, unit_price=None, unit=None)


def test_subscription_cost_price_enters_the_real_cost_but_paid_stays_the_fallback(monkeypatch):
    offers = [_offer("openrouter", pin=4, pout=20), _offer("kie", pin=1.6, pout=8), _offer("claude-pro", access="subscription")]
    monkeypatch.setattr(sel, "SUBSCRIPTION_COSTS", {("claude-pro", "claude-opus-5-5"): {"ratio": 0.017, "sub_id": "a"}})
    route = sel.chat_route(offers, 3.46)
    assert route["paid"]["provider"] == "kie" and route["paid"]["cost"] == pytest.approx(3.46 * 0.4)
    assert route["subscription_cost"]["cost"] == pytest.approx(3.46 * 0.017)
    assert sel.route_cost(route) == pytest.approx(3.46 * 0.017)
    assert sel.chat_route(offers, None)["subscription_cost"] is None                  # no list cost: nothing priced


def test_without_a_cost_price_the_route_is_unchanged(monkeypatch):
    offers = [_offer("openrouter", pin=4, pout=20), _offer("kie", pin=1.6, pout=8), _offer("claude-pro", access="subscription")]
    monkeypatch.setattr(sel, "SUBSCRIPTION_COSTS", {})
    route = sel.chat_route(offers, 3.46)
    assert route["subscription_cost"] is None and sel.route_cost(route) == pytest.approx(3.46 * 0.4)
