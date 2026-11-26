"""Thread pools whose tasks run in a copy of the submitter's context (contextvars): the run an owner message opened
follows its work into the pools, so Memory's calls made for it (decision, rerank) carry its trace label (payload
plan lot 0, owner 2026-11-23). Nothing else differs from ThreadPoolExecutor."""
from __future__ import annotations

import contextvars
from concurrent.futures import ThreadPoolExecutor


class Executor(ThreadPoolExecutor):
    def submit(self, fn, /, *args, **kwargs):
        return super().submit(contextvars.copy_context().run, fn, *args, **kwargs)
