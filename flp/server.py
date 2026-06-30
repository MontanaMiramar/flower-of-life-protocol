"""
Flower of Life Protocol v1.0 — Reference server + client (PROTOCOL.md §8.4, §7.5)

A zero-dependency reference server (stdlib http.server) exposing the six FLP
endpoints, plus a client whose every outbound fetch passes the §7.5 SSRF guard.

This is the artifact v0.1 never shipped: a runnable server, not a snippet in a
string. Production deployments may reimplement the same endpoints on FastAPI/etc;
the wire contract (§8) is what matters, not this transport.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from .agent import FLPAgent
from .identity import FLPVerifyError
from .net import validate_endpoint

_MAX_BODY = 256 * 1024   # response/request size cap (§7.5 step 4)


# --------------------------------------------------------------------------- #
# Server
# --------------------------------------------------------------------------- #

def make_handler(agent: FLPAgent):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):  # silence default logging
            pass

        def _send(self, code: int, payload: dict[str, Any]):
            data = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json(self) -> Optional[dict]:
            length = int(self.headers.get("Content-Length", 0))
            if length > _MAX_BODY:
                self._send(413, {"type": "error", "code": "validation_failed",
                                 "message": "body too large"})
                return None
            raw = self.rfile.read(length) if length else b"{}"
            try:
                return json.loads(raw)
            except Exception:  # noqa: BLE001
                self._send(400, {"type": "error", "code": "validation_failed",
                                 "message": "invalid JSON"})
                return None

        def _dispatch_post(self, handler):
            body = self._read_json()
            if body is None:
                return
            try:
                self._send(200, handler(body))
            except FLPVerifyError as e:
                # §8.6: signed-error semantics simplified to a code; no internals leaked.
                self._send(400, {"type": "error", "code": e.code, "message": str(e)})
            except Exception:  # noqa: BLE001
                self._send(500, {"type": "error", "code": "validation_failed",
                                 "message": "internal error"})

        def do_GET(self):
            if self.path == "/.well-known/flp-card":
                self._send(200, agent.signed_card())
            elif self.path == "/flp/status":
                self._send(200, agent.status())
            else:
                self._send(404, {"type": "error", "code": "validation_failed",
                                 "message": "not found"})

        def do_POST(self):
            if self.path == "/flp/encounter":
                self._dispatch_post(agent.handle_encounter)
            elif self.path == "/flp/respond":
                self._dispatch_post(agent.handle_respond)
            elif self.path == "/flp/outcome":
                self._dispatch_post(agent.handle_outcome)
            else:
                self._send(404, {"type": "error", "code": "validation_failed",
                                 "message": "not found"})

    return Handler


class FLPServer:
    """Threaded reference server wrapping one FLPAgent."""

    def __init__(self, agent: FLPAgent, host: str = "127.0.0.1", port: int = 0):
        self.agent = agent
        self._httpd = ThreadingHTTPServer((host, port), make_handler(agent))
        self.host, self.port = self._httpd.server_address[0], self._httpd.server_address[1]
        self._thread: Optional[threading.Thread] = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self):
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._httpd.shutdown()
        self._httpd.server_close()


# --------------------------------------------------------------------------- #
# Client (every fetch is SSRF-guarded — §7.5)
# --------------------------------------------------------------------------- #

class FLPClient:
    def __init__(self, *, allow_private: bool = False, timeout: float = 5.0):
        # allow_private=True ONLY for loopback dev/testing; never in production.
        self.allow_private = allow_private
        self.timeout = timeout

    def _request(self, url: str, method: str, payload: Optional[dict]) -> dict:
        validate_endpoint(url, allow_private=self.allow_private)   # §7.5 gate
        data = json.dumps(payload).encode() if payload is not None else None
        req = Request(url, data=data, method=method,
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read(_MAX_BODY + 1)
        except HTTPError as e:
            # §8.6 errors are returned envelopes the caller inspects, not
            # transport exceptions. Surface the error body if it is JSON.
            raw = e.read(_MAX_BODY + 1)
            try:
                return json.loads(raw)
            except Exception:  # noqa: BLE001
                raise FLPVerifyError("validation_failed", f"HTTP {e.code}") from e
        if len(raw) > _MAX_BODY:
            raise FLPVerifyError("validation_failed", "response too large")
        return json.loads(raw)

    def fetch_card(self, base_url: str) -> dict:
        return self._request(base_url.rstrip("/") + "/.well-known/flp-card", "GET", None)

    def status(self, base_url: str) -> dict:
        return self._request(base_url.rstrip("/") + "/flp/status", "GET", None)

    def encounter(self, base_url: str, my_signed_card: dict) -> dict:
        return self._request(base_url.rstrip("/") + "/flp/encounter", "POST", my_signed_card)

    def respond(self, base_url: str, signed_proposal: dict) -> dict:
        return self._request(base_url.rstrip("/") + "/flp/respond", "POST", signed_proposal)

    def outcome(self, base_url: str, signed_attestation: dict) -> dict:
        return self._request(base_url.rstrip("/") + "/flp/outcome", "POST", signed_attestation)
