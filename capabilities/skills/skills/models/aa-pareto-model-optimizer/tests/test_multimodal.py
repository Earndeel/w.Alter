from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "refresh_modalities.py"
SPEC = importlib.util.spec_from_file_location("aa_refresh_modalities", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _elo_header() -> list[str]:
    return [
        "",
        "Range",
        "Creator",
        "Model",
        "Elo",
        "95% CI",
        "Samples",
        "Arena Voices",
        "Released",
        "API Pricing 1",
    ]


def test_elo_task_keeps_quality_and_api_list_price_separate() -> None:
    spec = MODULE.TASK_SPECS["text_to_image"]
    rows = [
        _elo_header(),
        ["1", "1-2", "OpenAI", "GPT Image 2.5 Sunburst (max)", "1196", "-9/9", "13,586", "", "Sep 2026", "$210.7 /1k imgs"],
        ["2", "1-2", "Stability.ai", "Stable Diffusion 1.5\nOpen Weights", "455", "-13/13", "10,389", "", "Oct 2022", "$44.0 /1k imgs"],
    ]

    task = MODULE.build_task_payload(spec, rows, retrieved_at="2026-09-27T00:00:00+00:00")

    first, second = task["rows"]
    assert first["quality_score"] == 1196.0
    assert first["api_price_usd"] == 210.7
    assert first["api_price_unit"] == "1k imgs"
    assert first["open_weights"] is False
    assert second["model"] == "Stable Diffusion 1.5"
    assert second["open_weights"] is True
    assert task["cost"]["api_price_role"] == "reference_only"
    assert task["cost"]["pareto_frontier"]["status"] == "unavailable"
    assert all("benchmark_cost_per_task_usd" not in row for row in task["rows"])


def test_speech_to_speech_keeps_hourly_benchmark_cost_as_its_own_unit() -> None:
    spec = MODULE.TASK_SPECS["index"]
    rows = [
        [
            "Provider",
            "Model",
            "Speech to Speech Index",
            "Speech Reasoning %",
            "Conversational Dynamics %",
            "Agentic Performance %",
            "Arena Preference Elo",
            "Task Success Rate %",
            "Time to First Audio Seconds",
            "Cost per Hour of Input Audio USD, Big Bench Audio subset",
            "Price per Hour of Audio Input USD",
            "Price per Hour of Audio Output USD",
        ],
        [
            "Alibaba Cloud",
            "Qwen Audio 3.0 Realtime Plus",
            "66.8",
            "99%",
            "98.4%",
            "54.6%",
            "775",
            "77.8%",
            "1.54",
            "4.42",
            "0.03",
            "0.18",
        ],
        [
            "Alibaba Cloud",
            "Qwen3.5 Omni Plus Realtime",
            "-",
            "99%",
            "-",
            "-",
            "859",
            "62.0%",
            "2.64",
            "0.00",
            "0.16",
            "0.82",
        ],
    ]

    task = MODULE.build_task_payload(spec, rows, retrieved_at="2026-09-27T00:00:00+00:00")

    first, second = task["rows"]
    assert first["quality_score"] == 66.8
    assert first["speech_reasoning_percent"] == 99.0
    assert first["benchmark_cost_per_input_hour_usd"] == 4.42
    assert first["provider_price_per_hour_audio_input_usd"] == 0.03
    assert second["quality_score"] is None
    assert task["cost"]["benchmark_cost_status"] == "hourly_benchmark_metric_only"
    assert task["cost"]["pareto_frontier"]["status"] == "unavailable"
    assert "cost per benchmark task" in task["cost"]["pareto_frontier"]["reason"]


def test_all_modality_task_specs_are_separate_and_cover_requested_modules() -> None:
    specs = MODULE.TASK_SPECS

    assert {spec["module"] for spec in specs.values()} == {
        "tts",
        "speech_to_speech",
        "image",
        "video",
    }
    assert {spec["task"] for spec in specs.values()} == {
        "provider_voice",
        "index",
        "text_to_image",
        "text_to_video",
        "image_to_video",
    }
    assert all(spec["quality_direction"] == "higher_is_better" for spec in specs.values())
