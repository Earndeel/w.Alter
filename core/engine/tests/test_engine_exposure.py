"""Lot 3e (2026-11-27): `[native] exposure` — "python" offers the model only the kernel (100 % Unharnessed), "hybrid"
keeps direct tools; a bench test account may carry its own; a sub-agent follows its root. Offline."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from walter_engine import config  # noqa: E402
from walter_engine import engine as E  # noqa: E402
from walter_engine.tools import Result, Tool, builtin, obj  # noqa: E402


async def _noop(args, ex):
    return Result("ok")


def _engine(tmp_path, **kw):
    eng = E.Engine(config.Settings(state=tmp_path / "state", trusted_hosts=["portal.example"],
                                   login_url_file=tmp_path / "login-url", web_cookie_days=365, **kw))
    builtin.register(eng.registry)
    eng.registry.add(Tool("python", "Run Python.", obj({"code": {"type": "string"}}), _noop))
    return eng


def _close(eng):
    asyncio.run(eng.doors.close())
    asyncio.run(eng.llm.close())


def _names(schemas):
    return [s["function"]["name"] for s in schemas]


def test_hybrid_offers_every_listed_tool(tmp_path):
    eng = _engine(tmp_path)
    a = eng.create(cwd="/w", door="telegram", principal={"kind": "owner", "id": "monsieur"})
    names = _names(eng._tool_schemas(a))
    assert "python" in names and "read" in names and len(names) > 5
    _close(eng)


def test_python_exposure_offers_only_the_kernel_and_says_so(tmp_path):
    eng = _engine(tmp_path, exposure="python")
    a = eng.create(cwd="/w", door="telegram", principal={"kind": "owner", "id": "monsieur"})
    sch = eng._tool_schemas(a)
    assert _names(sch) == ["python"]
    assert sch[0]["function"]["description"].startswith(E.PYTHON_ONLY)
    assert eng.registry.tools["python"].description == "Run Python."          # the registry itself is unchanged
    _close(eng)


def test_bench_accounts_carry_their_arm_and_children_follow_the_root(tmp_path):
    eng = _engine(tmp_path, exposure_accounts={"bench-B": "python", "bench-A": "hybrid"})
    b = eng.create(cwd="/w", door="test", principal={"kind": "test", "id": "bench-B"})
    a = eng.create(cwd="/w", door="test", principal={"kind": "test", "id": "bench-A"})
    owner = eng.create(cwd="/w", door="telegram", principal={"kind": "owner", "id": "bench-B"})   # not a test account
    assert eng._exposure(b) == "python" and eng._exposure(a) == "hybrid" and eng._exposure(owner) == "hybrid"
    child = eng.create(cwd="/w", door="test", principal={"kind": "agent", "id": "x"}, depth=1, parent=b.sid)
    assert eng._exposure(child) == "python"
    _close(eng)


def test_s1_bubble_for_subagents_and_machines_only(tmp_path):
    """Python security S1 (2026-11-27): the owner's kernel keeps the engine's rights, sub-agents and machine callers
    get the unprivileged bubble, and each is told the rights it really has."""
    from walter_engine.tools import python as P
    eng = _engine(tmp_path, python_sandbox_for=("subagent", "machine"))
    eng.registry.tools["python"].description = P.DESCRIPTION
    owner = eng.create(cwd="/w", door="telegram", principal={"kind": "owner", "id": "monsieur"})
    child = eng.create(cwd="/w", door="telegram", principal={"kind": "owner", "id": "monsieur"}, depth=1, parent=owner.sid)
    guardian = eng.create(cwd="/w", door="api", principal={"kind": "machine", "id": "guardian-core"})
    assert eng.python.mode_for(owner) == "full"
    assert eng.python.mode_for(child) == "sandbox" and eng.python.mode_for(guardian) == "sandbox"
    text = lambda a: next(s["function"]["description"] for s in eng._tool_schemas(a) if s["function"]["name"] == "python")  # noqa: E731
    assert P.FULL_RIGHTS in text(owner) and P.SANDBOX_RIGHTS not in text(owner)
    assert P.SANDBOX_RIGHTS in text(guardian) and P.FULL_RIGHTS not in text(guardian)
    _close(eng)


def test_s1_is_off_by_default_and_python_sandbox_still_means_everyone(tmp_path):
    eng = _engine(tmp_path)
    m = eng.create(cwd="/w", door="api", principal={"kind": "machine", "id": "guardian-core"})
    assert eng.python.mode_for(m) == "full"
    _close(eng)
    eng = _engine(tmp_path, python="sandbox")
    o = eng.create(cwd="/w", door="telegram", principal={"kind": "owner", "id": "monsieur"})
    assert eng.python.mode_for(o) == "sandbox"
    _close(eng)
