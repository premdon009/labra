"""The container health check, against a stand-in app on this machine."""

import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from labra.probe import probe


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200 if self.path == "/readyz" else 503)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def app() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


@pytest.mark.item("W30")
def test_the_probe_passes_only_when_the_path_answers_200(app: str) -> None:
    assert probe("/readyz", app) is None
    assert probe("/healthz", app) == "/healthz answered 503"


@pytest.mark.item("W30")
def test_the_probe_fails_when_nothing_answers() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    problem = probe("/readyz", f"http://127.0.0.1:{free}", timeout=2)
    assert problem is not None
    assert problem.startswith("/readyz did not answer: ")
