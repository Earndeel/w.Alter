"""Lot E1: kernel/verify.py detects any drift of an installation (package added, removed or changed, exec bit,
symlink target, composition file) and the frozen manifest matches the frozen lock."""
import importlib.util
import json
from pathlib import Path

KERNEL = Path(__file__).resolve().parent.parent / "kernel"
spec = importlib.util.spec_from_file_location("kernel_verify", KERNEL / "verify.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


def _install(root: Path) -> Path:
    nm = root / "node_modules"
    (nm / "@deepseek-ai" / "dsh" / "bin").mkdir(parents=True)
    (nm / "@deepseek-ai" / "dsh" / "bin" / "dsh.js").write_text("run()\n")
    (nm / "left-pad").mkdir()
    (nm / "left-pad" / "index.js").write_text("module.exports = 1\n")
    (nm / ".bin").mkdir()
    (nm / ".bin" / "dsh").symlink_to("../@deepseek-ai/dsh/bin/dsh.js")
    (root / "package-lock.json").write_text(json.dumps({"packages": {"node_modules/@deepseek-ai/dsh": {
        "version": "0.2.0-rc.2", "integrity": "sha512-x"}}}))
    return root




def test_check_passes_on_identical_install_and_fails_on_each_kind_of_drift(tmp_path, monkeypatch):
    inst = _install(tmp_path / "a")
    manifest = tmp_path / "installed.json"
    monkeypatch.setattr(verify, "MANIFEST", manifest)
    manifest.write_text(json.dumps(verify.snapshot(inst, None)))
    assert verify.check(inst, None)["ok"]

    (inst / "node_modules" / "left-pad" / "index.js").write_text("module.exports = 2\n")
    assert verify.check(inst, None)["changed"] == ["left-pad"]
    (inst / "node_modules" / "left-pad" / "index.js").write_text("module.exports = 1\n")
    (inst / "node_modules" / "left-pad" / "index.js").chmod(0o755)
    assert verify.check(inst, None)["changed"] == ["left-pad"]
    (inst / "node_modules" / "left-pad" / "index.js").chmod(0o644)
    (inst / "node_modules" / ".bin" / "dsh").unlink()
    (inst / "node_modules" / ".bin" / "dsh").symlink_to("../left-pad/index.js")
    assert verify.check(inst, None)["changed"] == [".bin"]
    (inst / "node_modules" / ".bin" / "dsh").unlink()
    (inst / "node_modules" / ".bin" / "dsh").symlink_to("../@deepseek-ai/dsh/bin/dsh.js")
    (inst / "node_modules" / "extra-pkg").mkdir()
    r = verify.check(inst, None)
    assert r["extra"] == ["extra-pkg"] and not r["ok"]


def test_composition_drift_is_reported(tmp_path, monkeypatch):
    inst = _install(tmp_path / "a")
    home = tmp_path / "home"
    home.mkdir()
    (home / "cordis.patch.yml").write_text("a: 1\n")
    monkeypatch.setattr(verify, "composed", lambda install, h: {"web": "h1"})
    manifest = tmp_path / "installed.json"
    monkeypatch.setattr(verify, "MANIFEST", manifest)
    manifest.write_text(json.dumps(verify.snapshot(inst, home)))
    assert verify.check(inst, home)["ok"]
    (home / "cordis.patch.yml").write_text("a: 2\n")
    assert verify.check(inst, home)["compositions_changed"] == ["cordis.patch.yml"]
    (home / "cordis.patch.yml").write_text("a: 1\n")
    monkeypatch.setattr(verify, "composed", lambda install, h: {"web": "h2"})
    assert verify.check(inst, home)["composed_changed"] == ["web"]


def test_frozen_manifest_matches_frozen_lock():
    lock = json.loads((KERNEL / "package-lock.json").read_text())["packages"]
    manifest = json.loads((KERNEL / "installed.json").read_text())
    pkg = json.loads((KERNEL / "package.json").read_text())
    dsh = lock["node_modules/@deepseek-ai/dsh"]
    assert pkg["dependencies"]["@deepseek-ai/dsh"] == dsh["version"] == manifest["version"]  # exact pin, no range
    assert manifest["integrity"] == dsh["integrity"]
    installed = {k.rsplit("node_modules/", 1)[-1] for k in lock if k.startswith("node_modules/")
                 and k.count("node_modules/") == 1}
    top = {k for k in manifest["packages"] if k != ".bin"}
    assert top <= installed  # every installed top-level package comes from the lock
