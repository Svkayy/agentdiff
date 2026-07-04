"""Tiny local mock Anthropic API provider for the real demo.

Serves the minimum Anthropic messages endpoint that the SDK requires.
Start with start_mock_provider() and stop with stop_mock_provider().
"""
from __future__ import annotations

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

_server: HTTPServer | None = None
_thread: threading.Thread | None = None

_PORT = 18765


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: ANN002
        pass  # suppress access logs

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            req = json.loads(body) if body else {}
        except Exception:
            req = {}

        # Canned Anthropic messages response
        response = {
            "id": f"msg_{uuid.uuid4().hex[:24]}",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": "Fact-checked: the context appears accurate and relevant.",
                }
            ],
            "model": req.get("model", "claude-3-5-haiku-20241022"),
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 32, "output_tokens": 12},
        }

        payload = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')


def start_mock_provider(port: int = _PORT) -> int:
    """Start the mock provider thread. Returns the bound port."""
    global _server, _thread
    _server = HTTPServer(("127.0.0.1", port), _Handler)
    _thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _thread.start()
    return port


def stop_mock_provider() -> None:
    global _server, _thread
    if _server is not None:
        _server.shutdown()
        _server = None
    _thread = None
