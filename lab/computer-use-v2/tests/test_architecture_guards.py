from __future__ import annotations

import ast
from pathlib import Path

from adaptive_operator.capabilities import Primitive
from adaptive_operator.device_context import Platform
from adaptive_operator.front_door import Operation


RUNTIME = Path("adaptive_operator")


def _source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in RUNTIME.glob("*.py"))


def test_runtime_contains_no_app_recipes_or_unsupported_goal_terminal() -> None:
    source = _source().casefold()
    for forbidden in ("finder", "spotify", "photoshop", "youtube", "unsupported_goal"):
        assert forbidden not in source


def test_runtime_contains_no_browsing_engine_dependency() -> None:
    forbidden_roots = {"requests", "httpx", "scrapling", "camoufox", "playwright", "selenium"}
    imported: set[str] = set()
    for path in RUNTIME.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(forbidden_roots)


def test_primitives_stay_internal_behind_three_operation_front_door() -> None:
    assert len(Primitive.computer_use_runtime_primitives()) == 15
    assert len(tuple(Operation)) == 3


def test_contracts_are_multi_os_but_only_macos_is_live_in_lot20() -> None:
    assert {item.value for item in Platform} == {"macos", "windows", "android"}
    assert [item.value for item in Platform if item.live_in_lot20] == ["macos"]


def test_shadow_poll_import_graph_cannot_reach_transport_or_backend() -> None:
    pending = [RUNTIME / "shadow_spool_cli.py"]
    visited: set[Path] = set()
    forbidden_imports = {
        "subprocess",
        "socket",
        "urllib",
        "requests",
        "httpx",
        "adaptive_operator.macos_shadow",
    }
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in forbidden_imports
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert module not in forbidden_imports
                if module.startswith("adaptive_operator."):
                    candidate = RUNTIME / f"{module.rsplit('.', 1)[-1]}.py"
                    if candidate.exists():
                        pending.append(candidate)
        assert "CuaDriver" not in source
        assert "call_tool(" not in source
