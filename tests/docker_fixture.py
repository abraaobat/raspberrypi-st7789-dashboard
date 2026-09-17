"""Small fake Unix Engine for software/browser tests, never production Docker."""

import json
import socketserver
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path


SAMPLE_CONTAINERS = [
    {"Names": ["/homeassistant"], "State": "running", "Status": "Up 3 hours (healthy)", "Labels": {"private": "not-exported"}},
    {"Names": ["/jellyfin"], "State": "running", "Status": "Up 2 hours (unhealthy)", "Command": "not-exported"},
    {"Names": ["/pihole"], "State": "exited", "Status": "Exited (0) 1 hour ago", "Ports": [{"PrivatePort": 9999}]},
    {"Names": ["/node-red"], "State": "running", "Status": "Up 1 hour"},
    {"Names": ["/postgres"], "State": "paused", "Status": "Up 1 hour (Paused)"},
]


class FakeDocker:
    def __enter__(self):
        self.directory = tempfile.TemporaryDirectory(prefix="st-dkr-", dir="/tmp")
        self.path = str(Path(self.directory.name) / "engine.sock")
        self.calls = []
        self.responses = {"/version": (200, {"ApiVersion": "1.47"}),
                          "/v1.47/containers/json?all=1": (200, SAMPLE_CONTAINERS)}
        self.slow_headers = False
        self.content_length = "automatic"
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                fixture.calls.append({"method": "GET", "path": self.path})
                status, payload = fixture.responses.get(self.path, (404, {}))
                if fixture.slow_headers:
                    try:
                        for byte in b"HTTP/1.1 200 OK\r\nX-Slow: abcdefghijklmnopqrstuvwxyz":
                            self.wfile.write(bytes([byte]))
                            self.wfile.flush()
                            time.sleep(0.025)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
                body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                if fixture.content_length is not None:
                    self.send_header("Content-Length", str(len(body)) if fixture.content_length == "automatic" else fixture.content_length)
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def forbidden(self):
                fixture.calls.append({"method": self.command, "path": self.path})
                self.send_error(405)

            do_POST = do_PUT = do_DELETE = do_PATCH = forbidden

        class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True

        self.server = Server(self.path, Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()
