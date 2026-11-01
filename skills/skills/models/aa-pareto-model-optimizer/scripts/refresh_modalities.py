#!/usr/bin/env python3
"""Refresh AA TTS, speech-to-speech, image and video leaderboard data."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TASK_SPECS: dict[str, dict[str, Any]] = {
    "provider_voice": {
        "module": "tts",
        "task": "provider_voice",
        "url": "https://artificialanalysis.ai/text-to-speech/leaderboard/provider-voice",
        "kind": "elo_leaderboard",
        "table_marker": "API Pricing",
        "quality_metric": "Provider Voice Elo",
        "quality_unit": "Elo points",
        "quality_direction": "higher_is_better",
        "benchmark_cost_status": "not_published_for_benchmark_task",
    },
    "index": {
        "module": "speech_to_speech",
        "task": "index",
        "url": "https://artificialanalysis.ai/speech-to-speech",
        "kind": "speech_to_speech",
        "table_marker": "Speech to Speech Index",
        "quality_metric": "Speech to Speech Index",
        "quality_unit": "Index points",
        "quality_direction": "higher_is_better",
        "benchmark_cost_status": "hourly_benchmark_metric_only",
        "benchmark_cost_metric": "Cost per Hour of Input Audio (Big Bench Audio subset)",
        "benchmark_cost_unit": "USD per input-audio hour",
        "benchmark_cost_basis": "Fixed 40-question Big Bench Audio subset, normalized to an hourly basis",
    },
    "text_to_image": {
        "module": "image",
        "task": "text_to_image",
        "url": "https://artificialanalysis.ai/image/leaderboard/text-to-image",
        "kind": "elo_leaderboard",
        "table_marker": "API Pricing",
        "quality_metric": "Text-to-Image Arena Elo",
        "quality_unit": "Elo points",
        "quality_direction": "higher_is_better",
        "benchmark_cost_status": "not_published_for_benchmark_task",
    },
    "text_to_video": {
        "module": "video",
        "task": "text_to_video",
        "url": "https://artificialanalysis.ai/video/leaderboard/text-to-video",
        "kind": "elo_leaderboard",
        "table_marker": "API Pricing",
        "quality_metric": "Text-to-Video Arena Elo",
        "quality_unit": "Elo points",
        "quality_direction": "higher_is_better",
        "benchmark_cost_status": "not_published_for_benchmark_task",
    },
    "image_to_video": {
        "module": "video",
        "task": "image_to_video",
        "url": "https://artificialanalysis.ai/video/leaderboard/image-to-video",
        "kind": "elo_leaderboard",
        "table_marker": "API Pricing",
        "quality_metric": "Image-to-Video Arena Elo",
        "quality_unit": "Elo points",
        "quality_direction": "higher_is_better",
        "benchmark_cost_status": "not_published_for_benchmark_task",
    },
}

ELO_FIELDS = [
    "module",
    "task",
    "source_url",
    "rank",
    "rank_range",
    "provider",
    "model",
    "open_weights",
    "quality_metric",
    "quality_score",
    "quality_unit",
    "confidence_interval",
    "samples",
    "arena_voices",
    "released",
    "api_price_raw",
    "api_price_usd",
    "api_price_unit",
    "api_price_status",
    "speech_reasoning_percent",
    "conversational_dynamics_percent",
    "agentic_performance_percent",
    "arena_preference_elo",
    "task_success_rate_percent",
    "time_to_first_audio_seconds",
    "benchmark_cost_per_input_hour_usd",
    "provider_price_per_hour_audio_input_usd",
    "provider_price_per_hour_audio_output_usd",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_header(value: Any) -> str:
    """Normalize a rendered table header for robust column matching."""
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def clean_cell(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def find_column(headers: list[str], aliases: tuple[str, ...]) -> int | None:
    normalized = [normalize_header(header) for header in headers]
    targets = tuple(normalize_header(alias) for alias in aliases)
    for index, header in enumerate(normalized):
        if any(header == target or header.startswith(target) for target in targets):
            return index
    return None


def table_matches(rows: list[list[str]], spec: dict[str, Any]) -> bool:
    if not rows:
        return False
    headers = rows[0]
    if spec["kind"] == "elo_leaderboard":
        return (
            find_column(headers, ("model",)) is not None
            and find_column(headers, ("elo",)) is not None
            and find_column(headers, ("api pricing",)) is not None
        )
    return (
        find_column(headers, ("provider",)) is not None
        and find_column(headers, ("model",)) is not None
        and find_column(headers, ("speech to speech index",)) is not None
        and find_column(headers, ("cost per hour of input audio",)) is not None
    )


def select_task_table(tables: list[list[list[str]]], spec: dict[str, Any]) -> list[list[str]]:
    candidates = [table for table in tables if table_matches(table, spec) and len(table) > 1]
    if not candidates:
        raise RuntimeError(
            f"No AA table matched the expected {spec['task']} headers at {spec['url']}"
        )
    return max(candidates, key=len)


def parse_number(value: Any) -> float | None:
    text = clean_cell(value).replace(",", "")
    if not text or text in {"-", "—", "–", "N/A", "n/a"}:
        return None
    match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def parse_percent(value: Any) -> float | None:
    return parse_number(value)


def parse_api_price(value: Any) -> dict[str, Any]:
    raw = clean_cell(value).replace("\n", " ")
    lowered = raw.casefold()
    if not raw or lowered in {"-", "—", "–", "n/a", "not available"}:
        return {"api_price_raw": raw or None, "api_price_usd": None, "api_price_unit": None, "api_price_status": "not_listed"}
    if "no api" in lowered:
        status = "no_api_available"
    elif "coming soon" in lowered:
        status = "coming_soon"
    else:
        status = "unparsed"
    match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", raw)
    if match:
        price = parse_number(match.group(1))
        unit = raw.split("/", 1)[1].strip() if "/" in raw else None
        status = "listed"
    else:
        price = None
        unit = None
    return {
        "api_price_raw": raw,
        "api_price_usd": price,
        "api_price_unit": unit,
        "api_price_status": status,
    }


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return clean_cell(row[index])


def _elo_rows(spec: dict[str, Any], table_rows: list[list[str]]) -> list[dict[str, Any]]:
    headers = table_rows[0]
    columns = {
        "rank": find_column(headers, ("rank",)),
        "rank_range": find_column(headers, ("range",)),
        "provider": find_column(headers, ("creator", "provider")),
        "model": find_column(headers, ("model",)),
        "quality_score": find_column(headers, ("elo",)),
        "confidence_interval": find_column(headers, ("95% ci", "95 ci")),
        "samples": find_column(headers, ("samples",)),
        "arena_voices": find_column(headers, ("arena voices",)),
        "released": find_column(headers, ("released",)),
        "api_price": find_column(headers, ("api pricing",)),
    }
    if columns["rank"] is None and headers and not clean_cell(headers[0]):
        columns["rank"] = 0

    parsed: list[dict[str, Any]] = []
    for source_order, source_row in enumerate(table_rows[1:], start=1):
        model_text = _cell(source_row, columns["model"])
        if not model_text:
            continue
        open_weights = bool(re.search(r"\bopen\s+weights\b", model_text, flags=re.I))
        model = re.sub(r"(?:\s|\n)*\bopen\s+weights\b\s*$", "", model_text, flags=re.I).strip()
        if not model:
            continue
        api_price = parse_api_price(_cell(source_row, columns["api_price"]))
        parsed.append(
            {
                "source_order": source_order,
                "rank": parse_number(_cell(source_row, columns["rank"])) or source_order,
                "rank_range": _cell(source_row, columns["rank_range"]) or None,
                "provider": _cell(source_row, columns["provider"]) or None,
                "model": model,
                "open_weights": open_weights,
                "quality_metric": spec["quality_metric"],
                "quality_score": parse_number(_cell(source_row, columns["quality_score"])),
                "quality_unit": spec["quality_unit"],
                "confidence_interval": _cell(source_row, columns["confidence_interval"]) or None,
                "samples": parse_number(_cell(source_row, columns["samples"])),
                "arena_voices": _cell(source_row, columns["arena_voices"]) or None,
                "released": _cell(source_row, columns["released"]) or None,
                **api_price,
            }
        )
    if not parsed:
        raise RuntimeError(f"AA returned no usable rows for {spec['task']}")
    return parsed


def _speech_to_speech_rows(spec: dict[str, Any], table_rows: list[list[str]]) -> list[dict[str, Any]]:
    headers = table_rows[0]
    columns = {
        "provider": find_column(headers, ("provider",)),
        "model": find_column(headers, ("model",)),
        "quality_score": find_column(headers, ("speech to speech index",)),
        "speech_reasoning_percent": find_column(headers, ("speech reasoning",)),
        "conversational_dynamics_percent": find_column(headers, ("conversational dynamics",)),
        "agentic_performance_percent": find_column(headers, ("agentic performance",)),
        "arena_preference_elo": find_column(headers, ("arena preference",)),
        "task_success_rate_percent": find_column(headers, ("task success rate",)),
        "time_to_first_audio_seconds": find_column(headers, ("time to first audio",)),
        "benchmark_cost_per_input_hour_usd": find_column(headers, ("cost per hour of input audio",)),
        "provider_price_per_hour_audio_input_usd": find_column(headers, ("price per hour of audio input",)),
        "provider_price_per_hour_audio_output_usd": find_column(headers, ("price per hour of audio output",)),
    }
    required = ("provider", "model", "quality_score", "benchmark_cost_per_input_hour_usd")
    missing = [field for field in required if columns[field] is None]
    if missing:
        raise RuntimeError(f"AA speech-to-speech table missing columns: {', '.join(missing)}")

    parsed: list[dict[str, Any]] = []
    for source_order, source_row in enumerate(table_rows[1:], start=1):
        model = _cell(source_row, columns["model"])
        if not model:
            continue
        entry: dict[str, Any] = {
            "source_order": source_order,
            "provider": _cell(source_row, columns["provider"]) or None,
            "model": model,
            "quality_metric": spec["quality_metric"],
            "quality_score": parse_number(_cell(source_row, columns["quality_score"])),
            "quality_unit": spec["quality_unit"],
        }
        for field in (
            "speech_reasoning_percent",
            "conversational_dynamics_percent",
            "agentic_performance_percent",
            "arena_preference_elo",
            "task_success_rate_percent",
            "time_to_first_audio_seconds",
            "benchmark_cost_per_input_hour_usd",
            "provider_price_per_hour_audio_input_usd",
            "provider_price_per_hour_audio_output_usd",
        ):
            entry[field] = parse_number(_cell(source_row, columns[field]))
        parsed.append(entry)

    ranked = sorted(
        ((row["quality_score"], index) for index, row in enumerate(parsed) if row["quality_score"] is not None),
        key=lambda pair: (-pair[0], pair[1]),
    )
    rank_by_index: dict[int, int] = {}
    previous_score: float | None = None
    current_rank = 0
    for position, (score, index) in enumerate(ranked, start=1):
        if score != previous_score:
            current_rank = position
            previous_score = score
        rank_by_index[index] = current_rank
    for index, row in enumerate(parsed):
        row["rank"] = rank_by_index.get(index)
    if not parsed:
        raise RuntimeError("AA returned no usable rows for speech-to-speech")
    return parsed


def build_task_payload(
    spec: dict[str, Any], table_rows: list[list[str]], retrieved_at: str
) -> dict[str, Any]:
    cleaned_rows = [[clean_cell(cell) for cell in row] for row in table_rows]
    if not table_matches(cleaned_rows, spec):
        raise RuntimeError(f"AA table schema did not match task {spec['task']}")
    if spec["kind"] == "elo_leaderboard":
        rows = _elo_rows(spec, cleaned_rows)
        frontier_reason = (
            "AA publishes API list prices in output-specific units, not cost per benchmark task; "
            "the list prices are retained as reference data and are not substituted into a Pareto frontier."
        )
    else:
        rows = _speech_to_speech_rows(spec, cleaned_rows)
        frontier_reason = (
            "AA publishes a benchmark cost per input-audio hour, not cost per benchmark task; "
            "that hourly metric and provider price rates remain separate and are not substituted into a Pareto frontier."
        )
    return {
        "module": spec["module"],
        "task": spec["task"],
        "source_url": spec["url"],
        "retrieved_at": retrieved_at,
        "quality_metric": spec["quality_metric"],
        "quality_unit": spec["quality_unit"],
        "quality_direction": spec["quality_direction"],
        "ranking_basis": "AA published leaderboard order" if spec["kind"] == "elo_leaderboard" else "computed descending rank from AA index; ties share rank",
        "cost": {
            "benchmark_cost_status": spec["benchmark_cost_status"],
            "benchmark_cost_metric": spec.get("benchmark_cost_metric"),
            "benchmark_cost_unit": spec.get("benchmark_cost_unit"),
            "benchmark_cost_basis": spec.get("benchmark_cost_basis"),
            "api_price_role": "reference_only",
            "pareto_frontier": {"status": "unavailable", "reason": frontier_reason},
        },
        "row_count": len(rows),
        "rows": rows,
    }


def build_multimodal_snapshot(
    raw_tables: dict[str, list[list[str]]], retrieved_at: str | None = None
) -> dict[str, Any]:
    retrieved_at = retrieved_at or now_iso()
    modules: dict[str, dict[str, Any]] = {}
    for task_name, spec in TASK_SPECS.items():
        if task_name not in raw_tables:
            raise RuntimeError(f"No refreshed AA table supplied for task {task_name}")
        payload = build_task_payload(spec, raw_tables[task_name], retrieved_at)
        modules.setdefault(spec["module"], {"tasks": {}})["tasks"][task_name] = payload
    return {
        "schema_version": 1,
        "generated_at": retrieved_at,
        "source": "Artificial Analysis",
        "policy": {
            "quality_comparison": "within the same AA task leaderboard only",
            "api_prices_are_benchmark_costs": False,
            "cross_task_pareto_frontiers": False,
            "reason": "AA API price units differ by task and are not benchmark-task costs.",
        },
        "modules": modules,
    }


def fetch_task_table(browser: Any, spec: dict[str, Any], attempts: int = 3) -> list[list[str]]:
    last_error: Exception | None = None
    for _attempt in range(attempts):
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        try:
            response = page.goto(spec["url"], wait_until="domcontentloaded", timeout=60_000)
            if response is not None and response.status >= 400:
                raise RuntimeError(f"HTTP {response.status} from {spec['url']}")
            page.wait_for_function(
                """marker => [...document.querySelectorAll('table')].some(table =>
                    (table.innerText || '').includes(marker) && table.querySelectorAll('tr').length > 1)""",
                arg=spec["table_marker"],
                timeout=60_000,
            )
            tables = page.locator("table").evaluate_all(
                """tables => tables.map(table => Array.from(table.querySelectorAll('tr'))
                    .map(row => Array.from(row.querySelectorAll('th, td'))
                        .map(cell => (cell.innerText || '').trim()))
                    .filter(row => row.some(cell => cell.trim())))"""
            )
            return select_task_table(tables, spec)
        except Exception as exc:
            last_error = exc
        finally:
            page.close()
    raise RuntimeError(
        f"Unable to extract AA {spec['task']} table after {attempts} attempts: {last_error}"
    ) from last_error


def scrape_all_tables() -> dict[str, list[list[str]]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required; install it in the active Python environment") from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        try:
            return {
                task_name: fetch_task_table(browser, spec)
                for task_name, spec in TASK_SPECS.items()
            }
        finally:
            browser.close()


def default_output_dir() -> Path:
    try:
        from hermes_constants import get_hermes_home  # type: ignore

        home = Path(get_hermes_home())
    except Exception:
        home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).expanduser()
    return home / "cache" / "aa-pareto"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_csv(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ELO_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for module in snapshot["modules"].values():
            for task in module["tasks"].values():
                for row in task["rows"]:
                    writer.writerow(
                        {
                            "module": task["module"],
                            "task": task["task"],
                            "source_url": task["source_url"],
                            **row,
                        }
                    )
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        retrieved_at = now_iso()
        tables = scrape_all_tables()
        snapshot = build_multimodal_snapshot(tables, retrieved_at)
        output_dir = args.output_dir or default_output_dir()
        write_json(output_dir / "multimodal_latest.json", snapshot)
        write_csv(output_dir / "multimodal_latest.csv", snapshot)
    except Exception as exc:
        print(f"AA multimodal refresh ERROR: {exc}", file=sys.stderr)
        return 1
    if not args.quiet:
        counts = {
            task["task"]: task["row_count"]
            for module in snapshot["modules"].values()
            for task in module["tasks"].values()
        }
        print(f"AA multimodal data refreshed: {counts}; output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
