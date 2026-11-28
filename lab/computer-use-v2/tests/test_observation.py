from __future__ import annotations

import json

import pytest

from adaptive_operator.observation import (
    ElementRef,
    ObservationBuilder,
    ObservationDetail,
    ObservationRequest,
    RawElement,
    Rect,
)


def _raw_elements(count: int) -> list[RawElement]:
    return [
        RawElement(
            native_id=f"native-{index}",
            role="button",
            label=f"Item {index}",
            bounds=Rect(index, index, 20, 10),
            actionable=index % 2 == 0,
            attributes={"value": "large detail", "help": "not in compact summary"},
        )
        for index in range(count)
    ]


def test_minimal_observation_exposes_state_without_ax_dump_or_pixels():
    result = ObservationBuilder(max_elements=5).build(
        device_id="mac-main",
        app="Browser",
        window="Page",
        focused=True,
        snapshot_id="snap-1",
        generation=7,
        elements=_raw_elements(20),
        request=ObservationRequest(detail=ObservationDetail.MINIMAL),
    )

    payload = result.to_dict()
    assert payload["device"] == "mac-main"
    assert payload["app"] == "Browser"
    assert payload["element_count"] == 20
    assert "elements" not in payload
    assert "image" not in payload
    assert result.ax_chars == 0


def test_relevant_observation_is_bounded_and_uses_opaque_generation_refs():
    result = ObservationBuilder(max_elements=3).build(
        device_id="mac-main",
        app="Browser",
        window="Page",
        focused=False,
        snapshot_id="snap-1",
        generation=7,
        elements=_raw_elements(20),
        request=ObservationRequest(detail=ObservationDetail.RELEVANT, query="Item"),
    )

    assert len(result.elements) == 3
    assert result.truncated is True
    assert all(item.ref.startswith("e7-") for item in result.elements)
    assert result.next_detail is ObservationDetail.DETAILED
    assert result.ax_chars == len(json.dumps([item.to_dict() for item in result.elements], separators=(",", ":"), ensure_ascii=False))


def test_stale_or_unknown_detailed_ref_is_rejected():
    builder = ObservationBuilder(max_elements=4)
    with pytest.raises(ValueError, match="current snapshot"):
        builder.build(
            device_id="mac-main",
            app="Browser",
            window="Page",
            focused=False,
            snapshot_id="snap-2",
            generation=4,
            elements=_raw_elements(6),
            request=ObservationRequest(
                detail=ObservationDetail.DETAILED,
                refs=("e3-stale",),
            ),
        )


def test_pixels_disclosure_returns_crop_without_ax_elements():
    result = ObservationBuilder(max_elements=4).build(
        device_id="mac-main",
        app="Browser",
        window="Page",
        focused=False,
        snapshot_id="snap-2",
        generation=4,
        elements=_raw_elements(6),
        request=ObservationRequest(
            detail=ObservationDetail.PIXELS,
            crop=Rect(10, 20, 100, 80),
        ),
    )
    assert result.elements == ()
    assert result.ax_chars == 0
    assert result.image == {
        "kind": "crop",
        "bounds": [10, 20, 100, 80],
        "snapshot": "snap-2",
    }


def test_detailed_disclosure_requires_current_ref_and_returns_only_requested_element():
    builder = ObservationBuilder(max_elements=4)
    relevant = builder.build(
        device_id="mac-main",
        app="Browser",
        window="Page",
        focused=False,
        snapshot_id="snap-1",
        generation=3,
        elements=_raw_elements(6),
        request=ObservationRequest(detail=ObservationDetail.RELEVANT),
    )
    chosen: ElementRef = relevant.elements[0]

    detailed = builder.build(
        device_id="mac-main",
        app="Browser",
        window="Page",
        focused=False,
        snapshot_id="snap-1",
        generation=3,
        elements=_raw_elements(6),
        request=ObservationRequest(detail=ObservationDetail.DETAILED, refs=(chosen.ref,)),
    )

    assert len(detailed.elements) == 1
    assert detailed.elements[0].attributes["help"] == "not in compact summary"
    assert detailed.image is None
