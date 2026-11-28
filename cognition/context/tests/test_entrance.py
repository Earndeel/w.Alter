"""entrance: reduction of a large tool output on its way in (Claude Code PostToolUse), shadow records."""
import json
from dataclasses import replace

import pytest

from walter_context.compress import entrance as en


@pytest.fixture
def cfg():
    return en.load()


def bash_lines(n, bad_at=()):
    return "\n".join(("ERROR: disk full at step %d" % i) if i in bad_at else f"line {i} ok " + "x" * 40
                     for i in range(n))


def test_config_is_shadow_by_default_and_on_is_refused(cfg, tmp_path):
    assert cfg.mode == "shadow" and cfg.min_chars > cfg.head_chars + cfg.tail_chars
    toml = tmp_path / "c.toml"
    toml.write_text(en.DEFAULT_PATH.read_text().replace('mode = "shadow"', 'mode = "on"'))
    with pytest.raises(ValueError):
        en.load(toml)


def test_small_and_exempt_outputs_are_kept(cfg):
    assert en.reduce("Bash", "short", "toolu_1", cfg) is None
    assert en.reduce("Edit", "x" * 50_000, "toolu_1", cfg) is None


def test_head_tail_and_signal_lines_with_numbers(cfg):
    text = bash_lines(2000, bad_at=(700, 1300))
    cut = en.reduce("Bash", text, "toolu_42", cfg)
    out = cut["text"]
    assert cut["kept_chars"] < cut["orig_chars"] / 10
    assert out.startswith("[reduced Bash output") and "walter-context recover toolu_42" in out
    assert "line 0 ok" in out and "line 1999 ok" in out           # head and tail
    assert "701: ERROR: disk full at step 700" in out and "1301: ERROR" in out   # signal lines, 1-based numbers
    assert cut["signal"] == 2 and "lines" in out and "…]" in out  # hidden ranges are announced, never silent


def test_read_hint_points_back_to_the_file(cfg):
    cut = en.reduce("Read", bash_lines(1000), "toolu_7", cfg, path="/walter/x.py")
    assert "Read /walter/x.py with offset/limit" in cut["text"]


def test_huge_single_line_is_cut_by_characters(cfg):
    text = json.dumps({"blob": "A" * 60_000})
    cut = en.reduce("mcp__x__dump", text, "toolu_9", cfg)
    assert cut and "chars …]" in cut["text"] and cut["kept_chars"] < 3_000


@pytest.mark.parametrize("tool,response,expect", [
    ("Bash", {"stdout": "out", "stderr": "err"}, "out\nerr"),
    ("Read", {"type": "text", "file": {"filePath": "/a", "content": "body"}}, "body"),
    ("Read", {"type": "image", "file": {}}, ""),
    ("Grep", {"mode": "files_with_matches", "filenames": ["/a", "/b"]}, "/a\n/b"),
    ("WebFetch", {"result": "page", "code": 200}, "page"),
    ("mcp__walter__memory_search", [{"type": "text", "text": "hit"}], "hit"),
    ("mcp__walter__memory_search", "plain", "plain"),
])
def test_output_text_per_tool_shape(tool, response, expect):
    assert en.output_text(tool, response) == expect


def test_shadow_records_numbers_only_and_report_sums(cfg, tmp_path):
    secret_ish = bash_lines(1500, bad_at=(800,)) + "\nTOKEN-LIKE-CONTENT"
    ev = {"session_id": "s1", "tool_name": "Bash", "tool_use_id": "toolu_1", "tool_input": {"command": "x"},
          "tool_response": {"stdout": secret_ish, "stderr": ""}}
    row = en.handle(ev, cfg, tmp_path)
    assert row["session"] == "claude_code/vm/s1" and row["orig_chars"] > row["kept_chars"]
    en.handle({**ev, "tool_name": "Edit"}, cfg, tmp_path)          # exempt: not recorded
    en.handle({**ev, "tool_response": {"stdout": "tiny"}}, cfg, tmp_path)
    raw = "".join(p.read_text() for p in tmp_path.glob("entrance-*.jsonl"))
    assert raw.count("\n") == 1 and "TOKEN-LIKE" not in raw and "line 0" not in raw
    rep = en.report(tmp_path, 1, cfg)
    assert rep["outputs"] == 1 and rep["by_tool"]["Bash"]["saved_chars"] == row["orig_chars"] - row["kept_chars"]


def test_off_mode_does_nothing(cfg, tmp_path):
    ev = {"tool_name": "Bash", "tool_response": {"stdout": "y\n" * 9000}}
    assert en.handle(ev, replace(cfg, mode="off"), tmp_path) is None and not list(tmp_path.iterdir())


def test_output_the_host_already_persisted_is_left_alone(cfg, tmp_path):
    ev = {"tool_name": "Bash", "tool_use_id": "toolu_p", "tool_response": {
        "stdout": "z\n" * 20_000, "stderr": "", "persistedOutputPath": "/x/tool-results/a.txt", "persistedOutputSize": 9e5}}
    assert en.handle(ev, cfg, tmp_path) is None and not list(tmp_path.iterdir())
