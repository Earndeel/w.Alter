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
