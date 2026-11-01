from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "refresh.py"
SPEC = importlib.util.spec_from_file_location("aa_refresh_intelligence", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _rsc_script(payload: object) -> str:
    decoded = "c:" + json.dumps(payload, separators=(",", ":"))
    encoded = json.dumps(decoded)[1:-1]
    return f'self.__next_f.push([1,"{encoded}"])'


def test_parse_intelligence_rsc_finds_complete_language_model_context() -> None:
    models = [
        {
            "name": "Model A (max)",
            "shortName": "Model A (max)",
            "slug": "model-a-max",
            "intelligenceIndex": 51.25,
            "intelligenceIndexCostPerTask": {"cost": {"total": 0.125}},
        },
        {
            "name": "Model without intelligence",
            "slug": "model-empty",
            "intelligenceIndex": None,
            "intelligenceIndexCostPerTask": None,
        },
    ]
    payload = ["noise", {"children": [{"models": models}]}]

    assert MODULE.parse_intelligence_rsc(_rsc_script(payload)) == models


def test_parse_intelligence_rsc_merges_current_model_missing_from_catalog() -> None:
    catalog_model = {
        "name": "Catalog Model",
        "shortName": "Catalog Model",
        "slug": "catalog-model",
        "intelligenceIndex": 49.0,
        "intelligenceIndexCostPerTask": {"cost": {"total": 0.05}},
    }
    current_model = {
        "name": "GPT-5.6 Luna (max)",
        "shortName": "GPT-5.6 Luna (max)",
        "slug": "gpt-5-6-luna",
        "intelligenceIndex": 51.24,
        "intelligenceIndexCostPerTask": {"cost": {"total": 0.066}},
    }
    payload = {
        "children": {
            "models": [catalog_model],
            "currentModel": current_model,
        }
    }

    assert MODULE.parse_intelligence_rsc(_rsc_script(payload)) == [
        catalog_model,
        current_model,
    ]


def test_build_intelligence_records_uses_index_and_matching_task_cost() -> None:
    raw_models = [
        {
            "name": "Model A Adaptive Reasoning Max",
            "shortName": "Model A (max)",
            "slug": "model-a-max",
            "intelligenceIndex": 51.25,
            "intelligenceIndexCostPerTask": {"cost": {"total": 0.125}},
        },
        {
            "name": "Model without cost",
            "shortName": "Model without cost",
            "slug": "model-no-cost",
            "intelligenceIndex": 49.0,
            "intelligenceIndexCostPerTask": None,
        },
        {
            "name": "Non-language model",
            "slug": "non-language",
            "intelligenceIndex": None,
            "intelligenceIndexCostPerTask": None,
        },
    ]

    records = MODULE.build_intelligence_records(raw_models)

    assert records == [
        {
            "name": "Model A (max)",
            "slug": "model-a-max",
            "intelligence_index": 51.25,
            "aa_cost_per_task_intelligence_usd": 0.125,
            "intelligence_source_url": "https://artificialanalysis.ai/models/model-a-max",
            "intelligence_status": "ok",
        },
        {
            "name": "Model without cost",
            "slug": "model-no-cost",
            "intelligence_index": 49.0,
            "aa_cost_per_task_intelligence_usd": None,
            "intelligence_source_url": "https://artificialanalysis.ai/models/model-no-cost",
            "intelligence_status": "missing_cost",
        },
    ]


def test_validate_intelligence_anchor_rejects_incomplete_catalog() -> None:
    with pytest.raises(RuntimeError, match="anchor model gpt-5-6-luna is missing"):
        MODULE.validate_intelligence_anchor(
            [{"slug": "gpt-5-6-luna-high"}],
            "gpt-5-6-luna",
        )

    MODULE.validate_intelligence_anchor(
        [{"slug": "gpt-5-6-luna"}],
        "gpt-5-6-luna",
    )


def test_load_rsc_models_retries_with_fresh_contexts(monkeypatch) -> None:
    class FakePage:
        def __init__(self, browser) -> None:
            self.browser = browser

        def goto(self, *args, **kwargs) -> None:
            self.browser.navigation_attempts += 1
            if self.browser.navigation_attempts < 3:
                raise RuntimeError("transient navigation timeout")

        def wait_for_timeout(self, timeout_ms: int) -> None:
            assert timeout_ms == 0

        def evaluate(self, script: str) -> str:
            assert script == "extract-rsc"
            return "rsc-payload"

    class FakeContext:
        def __init__(self, browser) -> None:
            self.browser = browser
            self.closed = False

        def new_page(self) -> FakePage:
            return FakePage(self.browser)

        def close(self) -> None:
            self.closed = True

    class FakeBrowser:
        def __init__(self) -> None:
            self.navigation_attempts = 0
            self.contexts = []

        def new_context(self, **kwargs) -> FakeContext:
            context = FakeContext(self)
            self.contexts.append(context)
            return context

    monkeypatch.setattr(MODULE.time, "sleep", lambda seconds: None)
    browser = FakeBrowser()

    models = MODULE.load_rsc_models_with_retry(
        browser,
        url="https://example.test/models",
        viewport={"width": 1400, "height": 1200},
        extractor_js="extract-rsc",
        parser=lambda script: [{"script": script}],
        label="Intelligence",
        attempts=3,
        settle_timeout_ms=0,
    )

    assert models == [{"script": "rsc-payload"}]
    assert browser.navigation_attempts == 3
    assert len(browser.contexts) == 3
    assert all(context.closed for context in browser.contexts)



