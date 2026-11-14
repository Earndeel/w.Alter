from walter_memory import backup_bundle


def test_caller_patterns_exclude_rebuildable_paths(monkeypatch):
    monkeypatch.setattr(backup_bundle, "EXTRA_EXCLUDE", ("walter/colab/python", "root/.hermes/profiles/*/checkpoints"))
    assert backup_bundle.excluded("walter/colab/python")
    assert backup_bundle.excluded("walter/colab/python/cpython-3.13/bin/python3")
    assert backup_bundle.excluded("root/.hermes/profiles/hephaestus/checkpoints/abc")
    assert not backup_bundle.excluded("walter/colab/run.py")
    assert not backup_bundle.excluded("root/.hermes/profiles/hephaestus/config.yaml")


def test_no_caller_patterns_changes_nothing(monkeypatch):
    monkeypatch.setattr(backup_bundle, "EXTRA_EXCLUDE", ())
    assert not backup_bundle.excluded("walter/colab/python/x")
