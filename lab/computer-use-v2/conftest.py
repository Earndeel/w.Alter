"""Lets the study's tests run from Lab's root: `adaptive_operator` importable, and the working directory set to the
study folder (its tests open files by relative path, as in their original bundle)."""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


@pytest.fixture(autouse=True)
def _study_cwd(monkeypatch):
    monkeypatch.chdir(HERE)
