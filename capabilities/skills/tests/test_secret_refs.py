"""Vault values in skills become Walter Secrets placeholders (curator operator + write door), 2026-11-01."""
import re
from types import SimpleNamespace

from walter_skills import secret_refs

PASSWORD = "S3cret-pass-2026"
REGION = "eu-west-3"
UNKNOWN = "zzUnknownToken123"   # indexed by the fingerprints but no longer in the vault


def fake(monkeypatch):
    values = {PASSWORD, REGION, UNKNOWN}

    class M:
        def _load(self):
            return True

        def _hit(self, tok):
            return tok in values

    fp = SimpleNamespace(MASK="«secret:vault»", MIN_LEN=8, _SPLIT="=:&?/@#",
                         _TOKEN=re.compile(r"[^\s'\"`<>()\[\]{}|,;\\]+"), _matcher=M(),
                         worth_indexing=lambda v: isinstance(v, str) and len(v) >= 8,
                         status=lambda: {"ok": True})
    fp.scrub = lambda t: fp._TOKEN.sub(lambda m: fp.MASK if m.group() in values else m.group(), t)
    items = [{"id": "1b4e28ba-2fa1-11d2-883f-0016d3cca427", "name": "draw.walter-ai.cloud",
              "login": {"password": PASSWORD}},
             {"id": "6fa459ea-ee8a-3ca4-894e-db77e160355e", "name": "W.Alter · aws",
              "fields": [{"name": "region", "type": 0, "value": REGION}]}]
    vault = SimpleNamespace(VAULT=SimpleNamespace(items=lambda: items))
    monkeypatch.setattr(secret_refs, "_secrets", lambda: (fp, vault))
    return fp


def test_vault_values_become_placeholders_and_configuration_stays(monkeypatch):
    fake(monkeypatch)
    text = f"login with `{PASSWORD}` in region {REGION}; old key {UNKNOWN}\nPASS={PASSWORD}\n"
    out, n = secret_refs.to_placeholders(text)
    assert PASSWORD not in out and UNKNOWN not in out
    assert out.count("{{bw:draw.walter-ai.cloud:password}}") == 2
    assert REGION in out                      # a short visible field is configuration, not a secret
    assert "«secret:vault»" in out            # indexed but gone from the vault: generic mask, never clear text
    assert n == 3


def test_operator_rewrites_files_and_reports_counts_only(tmp_path, monkeypatch):
    fake(monkeypatch)
    d = tmp_path / "skills/web/site-login"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: site-login\ndescription: Use when logging in.\n---\npassword {PASSWORD}\n")
    files = secret_refs.scan([tmp_path / "skills"])
    assert files == [d / "SKILL.md"]
    r = secret_refs.fix(files)
    assert r == {"files": 1, "placeholders": 1, "generic_masks": 0}
    assert "{{bw:draw.walter-ai.cloud:password}}" in (d / "SKILL.md").read_text()


def test_the_door_stores_a_placeholder_not_the_value(tmp_path, monkeypatch):
    import subprocess
    from walter_skills import door, store
    fake(monkeypatch)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.setattr(store, "ROOT", tmp_path)
    monkeypatch.setattr(store, "DRAFTS", tmp_path / "drafts")
    md = f"---\nname: draw-login\ndescription: Use when logging in to the Excalidraw server.\n---\nPassword: {PASSWORD}\n"
    door.propose("draw-login", md, "learned while logging in to draw.walter-ai.cloud", runtime="test")
    written = next((tmp_path / "drafts").glob("draw-login@*/SKILL.md")).read_text()
    assert PASSWORD not in written and "{{bw:draw.walter-ai.cloud:password}}" in written
