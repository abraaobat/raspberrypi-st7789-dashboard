#!/usr/bin/env python3
"""Isolated browser fixture. Fake services/credentials; never reads production state."""
import argparse
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flask import jsonify
from waitress import serve
from web_app import create_app
from dashboard.source_templates import public_source_templates
from tests.docker_fixture import FakeDocker

FAKE_SECRET = "browser-fixture-only"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8093)
    args = parser.parse_args()
    calls = []
    samples = {item["id"]: item["sample"] for item in public_source_templates()}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, payload, status=200):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            calls.append({"method": "POST", "path": self.path})
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            self.reply({"session": {"valid": True, "sid": "fixture-session"}} if body.get("password") == FAKE_SECRET
                       else {"error": "denied"}, 200 if body.get("password") == FAKE_SECRET else 401)

        def do_DELETE(self):
            calls.append({"method": "DELETE", "path": self.path})
            self.reply({})

        def do_GET(self):
            calls.append({"method": "GET", "path": self.path})
            if self.path.startswith("/examples/") and self.path.removeprefix("/examples/") in samples:
                self.reply(samples[self.path.removeprefix("/examples/")])
            elif self.path == "/api/stats/summary":
                self.reply({"queries": {"total": 1000, "blocked": 245, "percent_blocked": 24.5},
                            "clients": {"active": 8}, "gravity": {"domains_being_blocked": 100000}})
            elif self.path.startswith("/api/states/") and self.headers.get("Authorization") == "Bearer " + FAKE_SECRET:
                entity = self.path.rsplit("/", 1)[-1]
                self.reply({"entity_id": entity, "state": "28.1" if entity.startswith("sensor.") else "on",
                            "attributes": {"friendly_name": "Temperatura" if entity.startswith("sensor.") else "Porta",
                                           "unit_of_measurement": "°C" if entity.startswith("sensor.") else ""}})
            else:
                self.reply({"error": "not found"}, 404)

    services = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=services.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory(prefix="st7789-browser-fixture-") as directory, FakeDocker() as docker:
        os.environ["ST7789_DOCKER_SOCKET"] = docker.path
        app = create_app({"STATE_DIR": directory, "SECRET_KEY": "isolated-browser-fixture-key"})

        @app.get("/fixture/status")
        def fixture_status():
            # Metadata is fake and deliberately excludes secrets, even in this fixture.
            return jsonify({"baseUrl": f"http://127.0.0.1:{services.server_port}", "calls": calls, "dockerCalls": docker.calls})

        print(f"Isolated control panel fixture on http://127.0.0.1:{args.port}", flush=True)
        try:
            serve(app, host="127.0.0.1", port=args.port, threads=4)
        finally:
            services.shutdown()
            services.server_close()


if __name__ == "__main__":
    main()
