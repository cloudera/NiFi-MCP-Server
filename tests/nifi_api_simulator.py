"""Local-only, deterministic NiFi REST API simulator for contract and safety tests.

This is a test double, not Apache NiFi and not evidence of real-server compatibility.
Run directly with: python tests/nifi_api_simulator.py --port 18787
It binds to loopback by default and never requires credentials or external services.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


class SimulatorState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.requests: list[dict[str, Any]] = []
        self.failures: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        self.delay_after_post_seconds = 0.0
        self.version = "2.6.0"

    def record(self, method: str, path: str) -> None:
        with self.lock:
            self.requests.append({"method": method, "path": path, "time": time.time()})

    def count(self, method: str, path: str) -> int:
        with self.lock:
            return sum(r["method"] == method and r["path"] == path for r in self.requests)

    def next_failure(self, path: str):
        with self.lock:
            queue = self.failures.get(path, [])
            return queue.pop(0) if queue else None


def _fixtures(state: SimulatorState) -> dict[str, dict[str, Any]]:
    return {
        "/nifi-api/flow/about": {"about": {"title": "Apache NiFi", "version": state.version, "timezone": "UTC"}},
        "/nifi-api/flow/process-groups/root": {
            "processGroupFlow": {"id": "root", "uri": "/nifi-api/flow/process-groups/root",
                "breadcrumb": {"id": "root", "name": "NiFi Flow"},
                "flow": {"processGroups": [], "remoteProcessGroups": [], "processors": [
                    {"id": "processor-001", "component": {"id": "processor-001", "name": "GenerateFlowFile", "type": "org.apache.nifi.processors.standard.GenerateFlowFile"}, "status": {"runStatus": "Stopped"}}
                ], "inputPorts": [], "outputPorts": [], "connections": [], "labels": []}}},
        "/nifi-api/process-groups/root/processors": {"processors": [
            {"id": "processor-001", "component": {"id": "processor-001", "name": "GenerateFlowFile", "type": "org.apache.nifi.processors.standard.GenerateFlowFile"}, "status": {"runStatus": "Stopped", "aggregateSnapshot": {"flowFilesOut": "0", "bytesOut": "0"}}}
        ]},
        "/nifi-api/process-groups/root/connections": {"connections": []},
        "/nifi-api/flow/controller/controller-services": {"controllerServices": []},
        "/nifi-api/flow/bulletin-board": {"bulletinBoard": {"bulletins": []}},
        "/nifi-api/flow/parameter-contexts": {"parameterContexts": []},
        "/nifi-api/flow/processor-types": {"processorTypes": []},
    }


def make_handler(state: SimulatorState):
    fixtures = _fixtures(state)

    class Handler(BaseHTTPRequestHandler):
        server_version = "NiFiApiSimulator/1.0"

        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _path(self) -> str:
            return urlparse(self.path).path

        def _authorised(self) -> bool:
            expected = getattr(self.server, "simulator_token", None)
            if not expected:
                return True
            return self.headers.get("Authorization") == f"Bearer {expected}"

        def do_GET(self) -> None:
            path = self._path()
            state.record("GET", path)
            if not self._authorised():
                self._send(401, {"message": "Unauthorized"})
                return
            failure = state.next_failure(path)
            if failure:
                self._send(failure[0], failure[1])
                return
            if path in fixtures:
                self._send(200, fixtures[path])
            elif path.startswith("/nifi-api/flow/process-groups/"):
                self._send(200, {"processGroupFlow": {"id": path.rsplit("/", 1)[-1], "flow": {"processors": [], "connections": [], "processGroups": []}}})
            else:
                self._send(404, {"message": "Simulator route not implemented", "path": path})

        def do_POST(self) -> None:
            path = self._path()
            state.record("POST", path)
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b""
            if not self._authorised():
                self._send(401, {"message": "Unauthorized"})
                return
            # Record the simulated mutation before delay: a client timeout must not cause retry.
            if state.delay_after_post_seconds:
                time.sleep(state.delay_after_post_seconds)
            self._send(201, {"revision": {"version": 1}, "component": {"id": "sim-created", "name": "simulated"}, "receivedBytes": len(body)})

        def do_PUT(self) -> None:
            path = self._path()
            state.record("PUT", path)
            if not self._authorised():
                self._send(401, {"message": "Unauthorized"})
                return
            self._send(200, {"revision": {"version": 2}, "component": {"id": "simulated"}})

        def do_DELETE(self) -> None:
            path = self._path()
            state.record("DELETE", path)
            if not self._authorised():
                self._send(401, {"message": "Unauthorized"})
                return
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()

    return Handler


def create_simulator(host: str = "127.0.0.1", port: int = 0, token: str | None = None):
    state = SimulatorState()
    server = ThreadingHTTPServer((host, port), make_handler(state))
    server.daemon_threads = True
    server.simulator_token = token
    return server, state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Loopback only by default; do not expose publicly")
    parser.add_argument("--port", type=int, default=18787)
    parser.add_argument("--token", default=None, help="Optional local test bearer token; avoid real credentials")
    args = parser.parse_args()
    server, _state = create_simulator(args.host, args.port, args.token)
    print(f"NiFi API SIMULATOR only — http://{args.host}:{server.server_port}/nifi-api", flush=True)
    print("Not a real NiFi instance; no flow execution or production compatibility is implied.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
