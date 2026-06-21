"""Redaction for captured request URLs.

``LLMRequestEvent.request_url`` is stored only for display/debugging. Some
providers carry credentials in the query string (Google Gemini uses
``?key=AIza...``), so the query is dropped before the URL is persisted to the
JSONL trajectory and the SQLite artifact.

This is non-destructive: provider matching (``match_provider``) and the
URL-keyed parsers (gemini/bedrock/azure) operate on the *live* request object,
never on this stored field, so dropping the query here does not affect capture.
"""
from urllib.parse import urlsplit, urlunsplit


def redact_url(url: str) -> str:
    """Return ``url`` with its query string removed (scheme+host+path kept).

    Best-effort: an unparseable URL is returned unchanged rather than raising,
    since this runs inside the capture hot path and must never break a call.
    """
    if not url:
        return url
    try:
        parts = urlsplit(url)
        if not parts.query:
            return url
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
    except Exception:
        return url
