"""walter-exit-default: the selector never keeps the owner's machine as the route once it is off its tunnel."""
import importlib.machinery
import importlib.util
from pathlib import Path
from urllib.parse import urlparse

SRC = Path(__file__).resolve().parent.parent / "bin" / "walter-exit-default"


def load(tmp_path, monkeypatch):
    monkeypatch.setenv("WALTER_EXIT_DEFAULT_STATE", str(tmp_path / "state.json"))
    loader = importlib.machinery.SourceFileLoader("walter_exit_default", str(SRC))
    spec = importlib.util.spec_from_loader("walter_exit_default", loader)
    X = importlib.util.module_from_spec(spec); loader.exec_module(X)
    X.cfg.update(listen=urlparse("socks5://127.0.0.1:1083"), primary=urlparse("socks5://127.0.0.1:1082"), ssh="mac",
                 vpn="Lucas", fallback="freebox-fr", fallback_port=1081)
    return X


def test_primary_closes_before_the_slow_fallback_start(tmp_path, monkeypatch):
    # 2026-11-21: the machine left its France tunnel; while `walter-wg-exit up` ran, the route stayed "primary" and
    # :1083 left from the machine's own (TH) IP. The route must already be closed while the fallback starts.
    X = load(tmp_path, monkeypatch)
    X.route = "primary"
    running = {"fb": False}
    seen = []

    def sh(*cmd, timeout=60):
        if cmd[:2] == ("walter-wg-exit", "up"):
            seen.append(X.route)          # what a new connection would get during the start
            running["fb"] = True
        return X.subprocess.CompletedProcess(cmd, 0, "up", "")

    monkeypatch.setattr(X, "sh", sh)
    monkeypatch.setattr(X, "primary_on_vpn", lambda: False)
    monkeypatch.setattr(X, "fallback_running", lambda: running["fb"])
    monkeypatch.setattr(X, "port_open", lambda h, p, timeout=2: True)
    assert X.decide() == "fallback"
    assert seen == ["none"]
    assert '"route": "none"' in (tmp_path / "state.json").read_text()


def test_unreachable_machine_also_closes_primary(tmp_path, monkeypatch):
    X = load(tmp_path, monkeypatch)
    X.route = "primary"
    monkeypatch.setattr(X, "sh", lambda *c, timeout=60: X.subprocess.CompletedProcess(c, 1, "", "fail"))
    monkeypatch.setattr(X, "primary_on_vpn", lambda: None)
    monkeypatch.setattr(X, "fallback_running", lambda: False)
    monkeypatch.setattr(X, "port_open", lambda h, p, timeout=2: True)
    assert X.decide() == "none"
    assert X.route == "none"


def test_machine_on_its_tunnel_keeps_primary(tmp_path, monkeypatch):
    X = load(tmp_path, monkeypatch)
    X.route = "primary"
    monkeypatch.setattr(X, "primary_on_vpn", lambda: True)
    monkeypatch.setattr(X, "fallback_running", lambda: False)
    monkeypatch.setattr(X, "port_open", lambda h, p, timeout=2: True)
    assert X.decide() == "primary"
    assert X.route == "primary"
