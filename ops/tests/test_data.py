"""Walter Clean data part: declarations are complete and typed, row filters are applied, markers are matched literally."""
import json
import re

import pytest

from walter_ops import data


def test_shipped_where_excludes_instance_rows():
    assert data.shipped_where({"class": "reference"}) == "true"
    assert data.shipped_where({"class": "reference", "instance_rows": "origin = 'manual'"}) == \
        "not coalesce((origin = 'manual'), false)"


def test_markers_are_matched_literally():
    rx = data.pattern(["a.b", "x-y@z.io"])
    assert re.search(rx, "contact x-y@z.io") and not re.search(rx, "aXb")


def test_declarations_refuse_an_unknown_class(tmp_path, monkeypatch):
    f = tmp_path / "data-classes.json"
    f.write_text(json.dumps({"version": 1, "module": "m", "tables": {"s.t": {"class": "maybe"}}}))
    monkeypatch.setattr(data.clean, "config", lambda: {"data": [{"module": "m"}]})
    monkeypatch.setattr(data.clean, "module_dir", lambda module, sub: f)
    with pytest.raises(ValueError):
        data.declarations()


def test_markers_come_from_the_instance(tmp_path, monkeypatch):
    (tmp_path / "instance.toml").write_text('[owner]\naddress = "Sir"\nemails = ["a@b.cd"]\n[privacy]\nmarkers = ["Zed", "x"]\n')
    monkeypatch.setattr(data.backup, "instance_root", lambda: tmp_path)
    assert data.markers() == ["Sir", "Zed", "a@b.cd"]          # too short markers are ignored
