"""HTTP response cassettes for deterministic CI capture.

The cassette layer is intentionally small: it records raw HTTP responses keyed
by method, URL, and request body, then replays them under an opt-in context
manager. Capture shims remain responsible for turning those responses into
AgentDiff trajectory events.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal

SCHEMA_VERSION = 1


class CassetteError(RuntimeError):
    """Base class for cassette failures."""


class CassetteMissError(CassetteError):
    """Raised when replay mode has no response for a request."""


class CassetteSchemaError(CassetteError):
    """Raised when a cassette cannot be read safely."""


Mode = Literal["record", "replay"]


@dataclass
class RecordedResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes


class HTTPCassette:
    """A JSONL response cassette keyed by normalized request fingerprint."""

    def __init__(self, path: str | Path, mode: Mode):
        self.path = Path(path)
        self.mode = mode
        self._records: dict[str, RecordedResponse] = {}
        if mode == "replay":
            self._records = self._load()
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    def lookup(self, method: str, url: str, body: bytes | None) -> RecordedResponse:
        key = request_key(method, url, body)
        try:
            return self._records[key]
        except KeyError as exc:
            raise CassetteMissError(f"no cassette recording for {method} {url}") from exc

    def record(
        self,
        *,
        method: str,
        url: str,
        body: bytes | None,
        status_code: int,
        headers: dict[str, str],
        response_body: bytes,
    ) -> None:
        if self.mode != "record":
            return
        payload = {
            "schema_version": SCHEMA_VERSION,
            "key": request_key(method, url, body),
            "request": {
                "method": method.upper(),
                "url": url,
                "body_sha256": _sha256(body or b""),
            },
            "response": {
                "status_code": int(status_code),
                "headers": dict(headers),
                "body_hex": response_body.hex(),
            },
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, sort_keys=True) + "\n")

    def _load(self) -> dict[str, RecordedResponse]:
        if not self.path.exists():
            raise CassetteMissError(f"cassette file does not exist: {self.path}")
        records: dict[str, RecordedResponse] = {}
        with open(self.path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                    if payload.get("schema_version") != SCHEMA_VERSION:
                        raise CassetteSchemaError(
                            f"unsupported cassette schema at line {line_no}"
                        )
                    response = payload["response"]
                    records[payload["key"]] = RecordedResponse(
                        status_code=int(response["status_code"]),
                        headers={str(k): str(v) for k, v in response.get("headers", {}).items()},
                        body=bytes.fromhex(response["body_hex"]),
                    )
                except CassetteSchemaError:
                    raise
                except Exception as exc:
                    raise CassetteSchemaError(
                        f"invalid cassette record at line {line_no}: {exc}"
                    ) from exc
        return records


_ACTIVE_CASSETTE: contextvars.ContextVar[HTTPCassette | None] = contextvars.ContextVar(
    "agentdiff_active_http_cassette", default=None
)


def active_cassette() -> HTTPCassette | None:
    return _ACTIVE_CASSETTE.get()


@contextmanager
def cassette(path: str | Path, mode: Mode) -> Iterator[HTTPCassette]:
    """Activate an HTTP cassette for the current context."""
    active = HTTPCassette(path, mode)
    token = _ACTIVE_CASSETTE.set(active)
    try:
        yield active
    finally:
        _ACTIVE_CASSETTE.reset(token)


def request_key(method: str, url: str, body: bytes | None) -> str:
    raw = json.dumps(
        {
            "method": method.upper(),
            "url": url,
            "body_sha256": _sha256(body or b""),
        },
        sort_keys=True,
    ).encode()
    return _sha256(raw)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
