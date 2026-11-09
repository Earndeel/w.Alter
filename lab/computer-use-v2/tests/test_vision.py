from __future__ import annotations

import pytest

from adaptive_operator.vision import (
    GeometryHint,
    LocateStatus,
    VisionBudget,
    VisionLocateRequest,
    VisionLocateResult,
    VisionPoint,
    validate_locate_result,
)
from adaptive_operator.observation import Rect


def test_locator_request_is_model_agnostic_and_budgeted():
    request = VisionLocateRequest(
        request_id="v1",
        snapshot_id="snap-2",
        target="unlabeled play icon",
        crop=Rect(100, 200, 400, 300),
        geometry_hints=(GeometryHint(ref="e2-a", bounds=Rect(120, 220, 40, 40)),),
        diff_base_snapshot="snap-1",
        budget=VisionBudget(max_latency_ms=500, max_image_pixels=300_000, max_output_tokens=64),
    )

    assert request.model_id is None
    assert request.click is False
    assert request.crop.width * request.crop.height <= request.budget.max_image_pixels


def test_located_result_must_be_bound_to_current_snapshot_and_inside_crop():
    request = VisionLocateRequest(
        request_id="v1",
        snapshot_id="snap-2",
        target="icon",
        crop=Rect(100, 200, 400, 300),
        budget=VisionBudget(500, 300_000, 64),
    )
    result = VisionLocateResult(
        request_id="v1",
        snapshot_id="snap-2",
        status=LocateStatus.LOCATED,
        confidence=0.93,
        point=VisionPoint(180, 260),
        evidence=("crop_match", "screen_diff"),
        latency_ms=80,
    )

    validated = validate_locate_result(request, result, minimum_confidence=0.85)

    assert validated is result


def test_stale_or_out_of_bounds_visual_location_fails_closed_before_click():
    request = VisionLocateRequest(
        request_id="v1",
        snapshot_id="snap-2",
        target="icon",
        crop=Rect(100, 200, 400, 300),
        budget=VisionBudget(500, 300_000, 64),
    )
    stale = VisionLocateResult(
        request_id="v1",
        snapshot_id="snap-1",
        status=LocateStatus.LOCATED,
        confidence=0.99,
        point=VisionPoint(180, 260),
        latency_ms=50,
    )

    with pytest.raises(ValueError, match="snapshot"):
        validate_locate_result(request, stale, minimum_confidence=0.8)

    outside = VisionLocateResult(
        request_id="v1",
        snapshot_id="snap-2",
        status=LocateStatus.LOCATED,
        confidence=0.99,
        point=VisionPoint(50, 50),
        latency_ms=50,
    )
    with pytest.raises(ValueError, match="crop"):
        validate_locate_result(request, outside, minimum_confidence=0.8)
