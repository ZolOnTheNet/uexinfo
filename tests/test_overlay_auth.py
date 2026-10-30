"""Garde-fous du serveur WebSocket : jeton de connexion, fichiers ouvrables."""
import asyncio
import socket

import pytest

from uexinfo.overlay import auth
from uexinfo.overlay.server import OverlayServer


def test_token_ok():
    assert auth.token_ok("/?t=abc", "abc")
    assert not auth.token_ok("/?t=abd", "abc")
    assert not auth.token_ok("/", "abc")
    assert not auth.token_ok("/?t=", "")          # serveur sans jeton : tout est refusé


def test_new_and_read_token(tmp_path):
    f = tmp_path / "sub" / "overlay.token"
    t = auth.new_token(f)
    assert len(t) >= 24 and auth.read_token(f) == t
    assert auth.new_token(f) != t                 # un jeton neuf par lancement
    assert auth.read_token(tmp_path / "absent") == ""


def test_openable(tmp_path):
    img = tmp_path / "capture.PNG"
    img.write_bytes(b"x")
    exe = tmp_path / "evil.exe"
    exe.write_bytes(b"x")
    assert auth.openable(str(img)) == img.resolve()
    assert auth.openable(str(exe)) is None
    assert auth.openable(str(tmp_path / "absent.png")) is None
    assert auth.openable(str(tmp_path)) is None   # un dossier n'est pas une image
    assert auth.openable("") is None


class _EchoServer(OverlayServer):
    """Serveur réduit à la poignée de main : le contexte n'est pas chargé."""
    async def handler(self, websocket):
        await websocket.send("ok")

    async def _periodic_status(self):
        return None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_server_rejects_connection_without_token():
    from websockets.asyncio.client import connect
    from websockets.exceptions import InvalidStatus

    async def scenario():
        srv = _EchoServer()
        srv.token = "secret"
        port = _free_port()
        task = asyncio.create_task(srv.serve("127.0.0.1", port))
        await asyncio.sleep(0.3)
        try:
            for path in ("/", "/?t=faux"):
                with pytest.raises(InvalidStatus) as exc:
                    async with connect(f"ws://127.0.0.1:{port}{path}"):
                        pass
                assert exc.value.response.status_code == 403
            async with connect(f"ws://127.0.0.1:{port}/?t=secret") as ws:
                assert await ws.recv() == "ok"
        finally:
            task.cancel()

    asyncio.run(scenario())
