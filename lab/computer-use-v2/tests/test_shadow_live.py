from __future__ import annotations

from adaptive_operator.shadow_live import ScenarioObservation, ScenarioSpec, build_scenario_matrix


def test_scenario_matrix_keeps_unobservable_states_unknown_or_skipped():
    matrix = build_scenario_matrix(
        captures=[
            ScenarioObservation("Safari", "Page", 50, "call-safari"),
            ScenarioObservation("Finder", "Downloads", 20, "call-finder"),
            ScenarioObservation("Hermes", "Hermes", 466, "call-rich"),
            ScenarioObservation("Cua Driver", "", 1, "call-sparse"),
        ],
        foreground_app="Finder",
        user_active=True,
        screen_locked=None,
        spec=ScenarioSpec(
            open_app_id="A_safari_open",
            open_app_name="Safari",
            foreground_app_id="B_finder_foreground",
            foreground_app_name="Finder",
            rich_ax_id="C_ax_rich",
            sparse_ax_id="D_ax_sparse",
            active_id="E_user_active",
            idle_id="F_user_idle",
            locked_id="G_screen_locked",
            external_boundary_id="H_walter_browse_boundary",
            external_provider="walter_browse",
        ),
    )

    by_id = {item.scenario_id: item for item in matrix}
    assert by_id["A_safari_open"].status == "observed"
    assert by_id["B_finder_foreground"].status == "observed"
    assert by_id["C_ax_rich"].selected_call_id == "call-rich"
    assert by_id["D_ax_sparse"].selected_call_id == "call-sparse"
    assert by_id["E_user_active"].status == "observed"
    assert by_id["F_user_idle"].status == "unknown"
    assert by_id["G_screen_locked"].status == "unknown"
    assert by_id["H_walter_browse_boundary"].status == "contract_observed"
    assert by_id["H_walter_browse_boundary"].external_provider == "walter_browse"
    assert all(item.mutations == 0 for item in matrix)
    assert all(item.screenshots == 0 for item in matrix)
