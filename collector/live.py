"""Live trajectory collector — buffers and ships trajectories to /v1/traffic."""
from __future__ import annotations

import logging
import threading
from typing import Callable

log = logging.getLogger("agentdiff.collector.live")


class LiveCollector:
    """Buffers live agent trajectories and flushes them to the AgentDiff platform.

    Usage::

        collector = LiveCollector(api_url="https://...", api_key="adk_...")
        collector.record(trajectory.model_dump(mode="json"))
        # auto-flushes at flush_every; call collector.flush() to force-flush

    Fail-soft design: any network or serialisation error during flush is logged
    as a warning and the batch is dropped (never buffered again).  The host
    application is never interrupted.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        *,
        flush_every: int = 20,
        post_fn: Callable | None = None,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._flush_every = flush_every
        self._post_fn = post_fn  # injectable for tests; defaults to httpx.post
        self._buffer: list[dict] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(self, trajectory: dict) -> None:
        """Append a trajectory dict to the buffer; auto-flush when threshold reached."""
        batch: list[dict] | None = None
        with self._lock:
            self._buffer.append(trajectory)
            if len(self._buffer) >= self._flush_every:
                batch = self._buffer
                self._buffer = []
        # flush outside the lock so lock is never held during I/O
        if batch is not None:
            self._post_batch(batch)

    def flush(self) -> None:
        """Force-flush all buffered trajectories immediately."""
        with self._lock:
            batch = self._buffer
            self._buffer = []
        if batch:
            self._post_batch(batch)

    def install(self) -> None:
        """Optional: install ambient capture shims.

        Attempts to wire up agentdiff.capture.activator for zero-instrumentation
        recording.  If the capture wiring is unavailable this is a no-op; the
        record() / flush() contract remains the primary API.
        """
        try:
            from agentdiff.capture import activator  # noqa: F401

            activator.install(callback=self.record)
            log.info("LiveCollector: ambient capture installed")
        except ImportError as exc:
            log.debug("LiveCollector.install(): ambient capture unavailable — %s", exc)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _post_batch(self, batch: list[dict]) -> None:
        """POST a batch to /v1/traffic; fail-soft on any error."""
        try:
            post = self._post_fn or _default_post
            response = post(
                f"{self._api_url}/v1/traffic",
                json={"trajectories": batch},
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            if hasattr(response, "status_code") and response.status_code >= 400:
                log.warning(
                    "LiveCollector: server returned %s — batch of %d dropped",
                    response.status_code,
                    len(batch),
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("LiveCollector: flush failed (%s) — batch of %d dropped", exc, len(batch))


def _default_post(url: str, **kwargs):
    """Default HTTP POST using httpx (lazy import so httpx is optional)."""
    import httpx

    return httpx.post(url, **kwargs)
