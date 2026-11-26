"""Payload plan lot 0 (2026-11-23): the run a message opened follows its work into the pools as Memory's trace label."""
from walter_context.preflight.service import _trace_run
from walter_context.threads import Executor
from walter_memory.llm import TRACE_RUN


def test_trace_label_set_and_carried_into_pools():
    pool = Executor(max_workers=2)
    assert TRACE_RUN.get() is None
    with _trace_run("01a20762-a6e4-7b78-96dd-f8e0ca25a92c"):
        assert pool.submit(TRACE_RUN.get).result() == "01a20762-a6e4-7b78-96dd-f8e0ca25a92c"
    assert TRACE_RUN.get() is None
    assert pool.submit(TRACE_RUN.get).result() is None
    with _trace_run(None):
        assert TRACE_RUN.get() is None
