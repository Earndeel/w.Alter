"""Generic scenario selection for a read-only shadow benchmark."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioObservation:
    app: str | None
    window: str | None
    element_count: int
    call_id: str


@dataclass(frozen=True)
class ScenarioSpec:
    open_app_id: str
    open_app_name: str
    foreground_app_id: str
    foreground_app_name: str
    rich_ax_id: str
    sparse_ax_id: str
    active_id: str
    idle_id: str
    locked_id: str
    external_boundary_id: str
    external_provider: str


@dataclass(frozen=True)
class ShadowScenario:
    scenario_id: str
    status: str
    reason: str
    selected_call_id: str | None = None
    external_provider: str | None = None
    mutations: int = 0
    screenshots: int = 0


def build_scenario_matrix(
    *,
    captures: list[ScenarioObservation],
    foreground_app: str | None,
    user_active: bool | None,
    screen_locked: bool | None,
    spec: ScenarioSpec,
) -> tuple[ShadowScenario, ...]:
    open_app = _first(
        captures,
        lambda item: (item.app or "").casefold() == spec.open_app_name.casefold(),
    )
    foreground_target = _first(
        captures,
        lambda item: (item.app or "").casefold()
        == spec.foreground_app_name.casefold(),
    )
    rich = max(captures, key=lambda item: item.element_count, default=None)
    nonempty = [item for item in captures if item.element_count > 0]
    sparse = min(nonempty, key=lambda item: item.element_count, default=None)
    target_is_foreground = bool(
        foreground_target is not None
        and (foreground_app or "").casefold()
        == spec.foreground_app_name.casefold()
    )
    return (
        _capture_scenario(spec.open_app_id, open_app, "target app capture reused from V1"),
        ShadowScenario(
            scenario_id=spec.foreground_app_id,
            status="observed" if target_is_foreground else "unknown",
            reason=(
                "target is the current foreground app"
                if target_is_foreground
                else "target foreground state was not observed"
            ),
            selected_call_id=(
                foreground_target.call_id if foreground_target is not None else None
            ),
        ),
        _capture_scenario(spec.rich_ax_id, rich, "richest persisted AX capture"),
        _capture_scenario(spec.sparse_ax_id, sparse, "sparsest non-empty persisted AX capture"),
        ShadowScenario(
            scenario_id=spec.active_id,
            status="observed" if user_active is True else "unknown",
            reason="recent input observed" if user_active is True else "active state unavailable",
        ),
        ShadowScenario(
            scenario_id=spec.idle_id,
            status="observed" if user_active is False else "unknown",
            reason="idle state observed" if user_active is False else "idle state not currently observed",
        ),
        ShadowScenario(
            scenario_id=spec.locked_id,
            status="observed" if screen_locked is True else "unknown",
            reason="locked state observed" if screen_locked is True else "lock state not safely testable",
        ),
        ShadowScenario(
            scenario_id=spec.external_boundary_id,
            status="contract_observed",
            reason="external capability remains outside Computer Use",
            external_provider=spec.external_provider,
        ),
    )


def _capture_scenario(
    scenario_id: str,
    item: ScenarioObservation | None,
    reason: str,
) -> ShadowScenario:
    return ShadowScenario(
        scenario_id=scenario_id,
        status="observed" if item is not None else "unknown",
        reason=reason if item is not None else "matching persisted V1 capture unavailable",
        selected_call_id=item.call_id if item is not None else None,
    )


def _first(items: list[ScenarioObservation], predicate) -> ScenarioObservation | None:
    return next((item for item in items if predicate(item)), None)
