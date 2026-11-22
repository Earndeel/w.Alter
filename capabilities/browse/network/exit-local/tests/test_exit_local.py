"""walter-exit-local: SOCKS5 + HTTP proxy, fail closed, per-host budget. A local fake upstream SOCKS and a local
HTTP origin stand in for the Mac and the web; nothing leaves the machine."""
import asyncio
import importlib.machinery
import importlib.util
import struct
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "bin" / "walter-exit-local"
loader = importlib.machinery.SourceFileLoader("walter_exit_local", str(SRC))
spec = importlib.util.spec_from_loader("walter_exit_local", loader)
X = importlib.util.module_from_spec(spec); loader.exec_module(X)


async def fake_socks(reader, writer):           # a minimal SOCKS5 upstream that connects directly (the "Mac")
    await reader.readexactly(3); writer.write(b"\x05\x00"); await writer.drain()
    _, _, _, atyp = await reader.readexactly(4)
    host = (await reader.readexactly((await reader.readexactly(1))[0])).decode() if atyp == 3 else \
        ".".join(map(str, await reader.readexactly(4)))
    port = struct.unpack(">H", await reader.readexactly(2))[0]
    r, w = await asyncio.open_connection(host, port)
    writer.write(b"\x05\x00\x00\x01" + b"\0" * 6); await writer.drain()
    await asyncio.gather(X.pipe(reader, w), X.pipe(r, writer))


async def origin(reader, writer):
    await reader.readuntil(b"\r\n\r\n")
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"); await writer.drain(); writer.close()


async def http_get_via(gate_port, origin_port):
    r, w = await asyncio.open_connection("127.0.0.1", gate_port)
    w.write(f"GET http://127.0.0.1:{origin_port}/x HTTP/1.1\r\nHost: 127.0.0.1\r\nProxy-Connection: keep-alive\r\n\r\n".encode())
    await w.drain(); data = await r.read(); w.close()
    return data


@pytest.fixture
def servers():
    async def start():
        up = await asyncio.start_server(fake_socks, "127.0.0.1", 0)
        org = await asyncio.start_server(origin, "127.0.0.1", 0)
        gate = await asyncio.start_server(X.handle, "127.0.0.1", 0)
        from urllib.parse import urlparse
        X.cfg.update(up=urlparse(f"socks5://127.0.0.1:{up.sockets[0].getsockname()[1]}"), per_min=2, per_day=100)
        return up, org, gate
    return start


def test_closed_gate_refuses_and_open_gate_forwards_with_a_budget(servers):
    async def scenario():
        up, org, gate = await servers()
        gport, oport = gate.sockets[0].getsockname()[1], org.sockets[0].getsockname()[1]
        X.minute.clear(); X.day.clear(); X.refused.clear()
        X.state.update(route="closed", why="the machine is on its France tunnel")
        assert b"403" in (await http_get_via(gport, oport)).split(b"\r\n")[0]
        X.state.update(route="open", why="test")
        assert (await http_get_via(gport, oport)).endswith(b"ok")
        assert (await http_get_via(gport, oport)).endswith(b"ok")
        third = await http_get_via(gport, oport)          # per_min = 2: the third connection to that host is refused
        assert b"403" in third.split(b"\r\n")[0] and X.refused["127.0.0.1"] == 1
        for s in (up, org, gate):
            s.close()
    asyncio.run(scenario())


def probe_with(monkeypatch, tmp_path, chromium_ip):
    """probe() with the network replaced: the France exit is 203.0.113.7, the local exit is closed."""
    import json
    from urllib.parse import urlparse
    monkeypatch.setattr(X, "load_config", lambda: {"listen": urlparse("socks5://127.0.0.1:1084")})
    monkeypatch.setattr(X, "france_ips", lambda: {"203.0.113.7"})
    monkeypatch.setattr(X, "exit_ip", lambda proxy, **kw: (chromium_ip, "FR" if chromium_ip else None)
                        if ":1083" in proxy else (None, None))
    monkeypatch.setattr(X, "sh", lambda *a, **k: X.subprocess.CompletedProcess(a, 0, "", ""))
    st = tmp_path / "state.json"; st.write_text(json.dumps({"route": "closed", "why": "mac unreachable"}))
    monkeypatch.setattr(X, "STATE", st)
    return X.probe()


def test_probe_flags_chromium_leaving_by_another_ip(monkeypatch, tmp_path, capsys):
    import json
    assert probe_with(monkeypatch, tmp_path, "198.51.100.9") == 1
    out = json.loads(capsys.readouterr().out)
    assert "Chromium's exit (:1083) is not the instance's France exit" in out["violations"]
    assert out["chromium_exit_unanswered"] is False


def test_probe_no_answer_from_chromium_exit_is_failed_closed_not_a_violation(monkeypatch, tmp_path, capsys):
    # 2026-11-20: the selector refused while the owner's machine flapped; the probe read "no IP" as a violation.
    import json
    probe_with(monkeypatch, tmp_path, None)
    out = json.loads(capsys.readouterr().out)
    assert not any("Chromium" in v for v in out["violations"])
    assert out["chromium_exit_unanswered"] is True


def test_exit_ip_falls_back_to_a_second_lookup_service(monkeypatch):
    calls = []
    def fake_sh(*cmd, **kw):
        calls.append(cmd[-1])
        body = "" if "ipinfo" in cmd[-1] else '{"ip": "203.0.113.7", "country_iso": "FR"}'
        return X.subprocess.CompletedProcess(cmd, 0, body, "")
    monkeypatch.setattr(X, "sh", fake_sh)
    assert X.exit_ip("socks5h://127.0.0.1:1083") == ("203.0.113.7", "FR")
    assert len(calls) == 2


def test_exit_ip_none_when_nothing_answers_through_the_exit(monkeypatch):
    monkeypatch.setattr(X, "sh", lambda *cmd, **kw: X.subprocess.CompletedProcess(cmd, 97, "", ""))
    monkeypatch.setattr(X.time, "sleep", lambda s: None)
    assert X.exit_ip("socks5h://127.0.0.1:1083") == (None, None)


def _decide_with(monkeypatch, *, forbidden, on_vpn, mac_ip, server="192.0.2.1"):
    from urllib.parse import urlparse
    X.cfg.clear()
    X.cfg.update(ssh="mac", vpn="Lucas", vpn_forbidden=forbidden, up=urlparse("socks5://127.0.0.1:1082"))
    X.state.update(ip=None, checked_ip_at=0.0, on_vpn=None, is_france_exit=False)
    monkeypatch.setattr(X, "mac_on_vpn", lambda: on_vpn)
    monkeypatch.setattr(X, "port_open", lambda *a, **k: True)
    monkeypatch.setattr(X, "exit_ip", lambda proxy, **kw: (mac_ip, "FR"))
    monkeypatch.setattr(X, "france_ips", lambda: {"203.0.113.7"})
    monkeypatch.setattr(X, "server_ip", lambda: server)
    return X.decide()


def test_the_mac_on_its_wireguard_tunnel_keeps_camoufox_open(monkeypatch):
    """Monsieur 2026-11-22: « le Camoufox passe par le Mac quelle que soit la connexion, même sur WireGuard »."""
    route, why = _decide_with(monkeypatch, forbidden=False, on_vpn=True, mac_ip="203.0.113.7")
    assert route == "open" and "Lucas" in why


def test_an_instance_that_forbids_the_tunnel_still_closes(monkeypatch):
    assert _decide_with(monkeypatch, forbidden=True, on_vpn=True, mac_ip="203.0.113.7")[0] == "closed"


def test_never_the_servers_own_ip(monkeypatch):
    route, why = _decide_with(monkeypatch, forbidden=False, on_vpn=False, mac_ip="192.0.2.1")
    assert route == "closed" and "server" in why
