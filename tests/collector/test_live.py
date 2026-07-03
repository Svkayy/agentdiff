"""Tests for collector/live.py LiveCollector."""
from __future__ import annotations

from unittest.mock import MagicMock


from collector.live import LiveCollector


# ---------------------------------------------------------------------------
# record() buffers trajectories
# ---------------------------------------------------------------------------


def test_record_buffers_trajectories():
    """record() adds to internal buffer when below flush threshold."""
    collector = LiveCollector(api_url="http://localhost", api_key="adk_test", flush_every=5)
    collector.record({"events": [], "id": "1"})
    collector.record({"events": [], "id": "2"})

    assert len(collector._buffer) == 2


# ---------------------------------------------------------------------------
# auto-flush at threshold
# ---------------------------------------------------------------------------


def test_record_autoflushes_at_threshold():
    """record() auto-flushes when buffer reaches flush_every."""
    posted_batches = []

    def fake_post(url, **kwargs):
        posted_batches.append(kwargs["json"]["trajectories"])
        resp = MagicMock()
        resp.status_code = 202
        return resp

    collector = LiveCollector(
        api_url="http://localhost", api_key="adk_test", flush_every=3, post_fn=fake_post
    )

    collector.record({"id": "a"})
    collector.record({"id": "b"})
    assert len(posted_batches) == 0  # not flushed yet
    collector.record({"id": "c"})   # triggers flush

    assert len(posted_batches) == 1
    assert len(posted_batches[0]) == 3
    assert collector._buffer == []  # buffer cleared


def test_flush_posts_bearer_token():
    """flush() POSTs with Authorization: Bearer header."""
    posted_headers = {}

    def fake_post(url, **kwargs):
        posted_headers.update(kwargs.get("headers", {}))
        resp = MagicMock()
        resp.status_code = 202
        return resp

    collector = LiveCollector(
        api_url="http://localhost", api_key="adk_my_key", flush_every=100, post_fn=fake_post
    )
    collector.record({"id": "x"})
    collector.flush()

    assert "Authorization" in posted_headers
    assert posted_headers["Authorization"] == "Bearer adk_my_key"


def test_flush_sends_to_correct_url():
    """flush() sends POST to {api_url}/v1/traffic."""
    posted_urls = []

    def fake_post(url, **kwargs):
        posted_urls.append(url)
        resp = MagicMock()
        resp.status_code = 202
        return resp

    collector = LiveCollector(
        api_url="https://api.example.com",
        api_key="adk_k",
        flush_every=100,
        post_fn=fake_post,
    )
    collector.record({"id": "1"})
    collector.flush()

    assert posted_urls == ["https://api.example.com/v1/traffic"]


# ---------------------------------------------------------------------------
# fail-soft: error during flush swallows exception and clears buffer
# ---------------------------------------------------------------------------


def test_flush_error_swallowed_buffer_cleared():
    """flush() on network error does NOT raise; buffer is cleared (drop the batch)."""

    def failing_post(url, **kwargs):
        raise ConnectionError("network down")

    collector = LiveCollector(
        api_url="http://localhost", api_key="adk_test", flush_every=100, post_fn=failing_post
    )
    collector.record({"id": "1"})
    collector.record({"id": "2"})
    assert len(collector._buffer) == 2

    # Should not raise
    collector.flush()

    # Buffer cleared (batch dropped)
    assert collector._buffer == []


def test_autoflush_error_swallowed():
    """auto-flush at threshold does not raise on network error."""

    def failing_post(url, **kwargs):
        raise RuntimeError("boom")

    collector = LiveCollector(
        api_url="http://localhost", api_key="adk_test", flush_every=2, post_fn=failing_post
    )

    # Should not raise even on failing post
    collector.record({"id": "1"})
    collector.record({"id": "2"})  # triggers auto-flush
    # No exception raised, buffer is cleared
    assert collector._buffer == []


# ---------------------------------------------------------------------------
# flush() with empty buffer is a no-op
# ---------------------------------------------------------------------------


def test_flush_empty_buffer_noop():
    """flush() with empty buffer does not call post_fn."""
    post_called = []

    def fake_post(url, **kwargs):
        post_called.append(True)
        resp = MagicMock()
        resp.status_code = 202
        return resp

    collector = LiveCollector(
        api_url="http://localhost", api_key="adk_k", flush_every=10, post_fn=fake_post
    )
    collector.flush()

    assert post_called == []
