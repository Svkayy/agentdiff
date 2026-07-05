"""Redaction for captured request/response data.

Everything captured by the HTTP and SDK shims — URLs, headers, raw bodies, and
the provider-normalized ``CanonicalLLMCall`` (system prompt, messages, tool
args, response text) — passes through this module immediately before an event
is constructed. No shim persists request/response data without calling into
one of these functions first.

Modes (``RedactionConfig.mode``, see ``agentdiff.config``):

* ``"standard"`` (default): known secret patterns (API keys, bearer tokens,
  PEM blocks, etc.) are masked wherever they appear in text/bodies/canonical
  fields; sensitive headers (Authorization, X-Api-Key, Api-Key, Cookie) are
  dropped. Message/system/tool content is otherwise stored as captured.
* ``"strict"``: everything standard mode does, **plus** message and system
  content is replaced with a ``sha256:<hex>`` digest of the original text —
  roles, message counts, tool names, and structure are preserved so
  before/after diffing still works, but the actual conversation content is
  never persisted.
* ``"off"``: redaction is FULLY DISABLED. No pattern masking, no header
  stripping — nothing. This is a deliberate escape hatch for local debugging
  only; it is the caller's responsibility to never ship a config with
  ``mode: "off"`` anywhere secrets might end up in a shared trajectory file.
  There is no partial-off behavior: "off" does not mean "still redact
  Authorization" — it means everything downstream from these functions is
  passed through byte-for-byte / value-for-value.

``redact_url`` (query-string stripping) is unrelated to ``RedactionConfig``
and always runs regardless of mode — see its own docstring.
"""
from __future__ import annotations

import contextvars
import hashlib
import re
from typing import TYPE_CHECKING, Mapping, overload
from urllib.parse import urlsplit, urlunsplit

if TYPE_CHECKING:
    from agentdiff.capture.events import CanonicalLLMCall
    from agentdiff.config import RedactionConfig


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


# ---------------------------------------------------------------------------
# Secret patterns
# ---------------------------------------------------------------------------

_MASK = "[REDACTED]"

SECRET_PATTERNS: list[re.Pattern] = [
    # OpenAI-style API keys, e.g. sk-abcdefghijklmnopqrstuvwx0123456789
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    # Anthropic API keys, e.g. sk-ant-api03-...
    re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{10,}\b"),
    # Slack tokens: xoxb-, xoxp-, xoxa-, xoxr-, xoxs-
    re.compile(r"\bxox[bpars]-[A-Za-z0-9\-]{10,}\b"),
    # Bearer tokens in Authorization-style header values.
    re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]{8,}=*"),
    # AWS access key IDs.
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    # PEM-encoded key/cert blocks (any BEGIN/END pair).
    re.compile(r"-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----", re.DOTALL),
    # Generic `api_key: ...` / `api-key=...` / `apikey=...` assignments.
    re.compile(r"\bapi[_-]?key\s*[:=]\s*\S+", re.IGNORECASE),
]

# Headers that always carry credentials. Dropped/masked in standard AND
# strict modes — never persisted verbatim regardless of body redaction mode.
_ALWAYS_SENSITIVE_HEADERS = {"authorization", "x-api-key", "api-key", "cookie"}


def _compile_extra_patterns(cfg: "RedactionConfig") -> list[re.Pattern]:
    patterns = []
    for raw in cfg.patterns:
        try:
            patterns.append(re.compile(raw))
        except re.error:
            continue  # Never let a bad user pattern break capture.
    return patterns


def redact_text(text: str, cfg: "RedactionConfig") -> str:
    """Mask any known or user-configured secret pattern found in ``text``.

    ``mode == "off"`` is a full bypass: ``text`` is returned unchanged. This
    is the only function that needs to check "off" explicitly — every other
    redact_* helper in this module funnels through here (or is itself a
    no-op check) so the bypass is centralized.
    """
    if not text:
        return text
    if cfg.mode == "off":
        return text

    out = text
    for pattern in SECRET_PATTERNS:
        out = pattern.sub(_MASK, out)
    for pattern in _compile_extra_patterns(cfg):
        out = pattern.sub(_MASK, out)
    return out


def redact_headers(headers: Mapping[str, str], cfg: "RedactionConfig") -> dict[str, str]:
    """Drop credential-bearing headers.

    Authorization, X-Api-Key, Api-Key, and Cookie (case-insensitive) are
    always removed in standard AND strict modes, plus any header named in
    ``cfg.redact_fields``. ``mode == "off"`` returns ``headers`` unchanged —
    see the module docstring: off means off.
    """
    if cfg.mode == "off":
        return dict(headers)

    drop_names = set(_ALWAYS_SENSITIVE_HEADERS) | {f.lower() for f in cfg.redact_fields}
    return {k: v for k, v in headers.items() if k.lower() not in drop_names}


@overload
def redact_body(body: bytes, cfg: "RedactionConfig") -> bytes: ...
@overload
def redact_body(body: str, cfg: "RedactionConfig") -> str: ...
def redact_body(body: "bytes | str", cfg: "RedactionConfig") -> "bytes | str":
    """Mask secret patterns found anywhere in a raw request/response body.

    Works on both ``bytes`` and ``str`` and preserves the input type. Best
    effort: bodies are treated as opaque text for pattern matching, no JSON
    parsing is attempted (unknown-provider bodies may not even be JSON).
    """
    if cfg.mode == "off":
        return body

    if isinstance(body, bytes):
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            return body  # Binary payload: nothing text-shaped to redact.
        return redact_text(text, cfg).encode("utf-8")

    return redact_text(body, cfg)


def hash_content(content) -> str:
    """Return a ``sha256:<hex>`` digest for arbitrary message/system content.

    Non-string content (e.g. Anthropic content-block lists) is stringified
    first via ``str()`` so strict mode never raises on unusual shapes.
    """
    if not isinstance(content, str):
        content = str(content)
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def redact_nested(value, cfg: "RedactionConfig"):
    """Recursively redact every string found inside ``value``.

    Handles arbitrarily nested combinations of ``dict``/``list``/``str`` —
    e.g. Anthropic/OpenAI content-block lists (``[{"type": "text", "text":
    "..."}]``) and nested ``tool_result`` blocks — while preserving the
    original structure and keys. Non-string/list/dict leaves (numbers, bools,
    ``None``) are returned unchanged. Shared by standard-mode message-content
    redaction and tool-arg/tool-delta redaction so there is exactly one place
    that walks nested capture payloads.
    """
    if isinstance(value, str):
        return redact_text(value, cfg)
    if isinstance(value, dict):
        return {k: redact_nested(v, cfg) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_nested(v, cfg) for v in value]
    return value


def _redact_message(message: dict, cfg: "RedactionConfig") -> dict:
    out = dict(message)
    content = out.get("content")
    if cfg.mode == "strict":
        if content is not None:
            out["content"] = hash_content(content)
    elif isinstance(content, str):
        out["content"] = redact_text(content, cfg)
    elif isinstance(content, (list, dict)):
        out["content"] = redact_nested(content, cfg)
    return out


def _redact_tool_use_blocks(blocks: list[dict], cfg: "RedactionConfig") -> list[dict]:
    redacted = []
    for block in blocks:
        new_block = dict(block)
        args = new_block.get("args")
        if isinstance(args, (dict, list, str)):
            new_block["args"] = redact_nested(args, cfg)
        redacted.append(new_block)
    return redacted


def redact_canonical(call: "CanonicalLLMCall", cfg: "RedactionConfig") -> "CanonicalLLMCall":
    """Return a copy of ``call`` with secrets masked in system/messages/tool args.

    In ``strict`` mode, ``system``, each message's ``content``, and
    ``response_text`` are replaced with ``sha256:<hex>`` digests of the
    original text — roles, message order/count, tool names, and metadata
    (usage, stop_reason, sampling_params) are left intact so trajectories
    stay diffable without retaining conversation content.

    ``mode == "off"`` returns ``call`` unchanged (not even copied) — off
    means off, see the module docstring.
    """
    if cfg.mode == "off":
        return call

    system = call.system
    if system is not None:
        system = hash_content(system) if cfg.mode == "strict" else redact_text(system, cfg)

    messages = [_redact_message(m, cfg) for m in call.messages]

    response_text = call.response_text
    if response_text is not None:
        response_text = (
            hash_content(response_text) if cfg.mode == "strict" else redact_text(response_text, cfg)
        )

    tool_use_blocks = _redact_tool_use_blocks(call.tool_use_blocks, cfg)

    return call.model_copy(update={
        "system": system,
        "messages": messages,
        "response_text": response_text,
        "tool_use_blocks": tool_use_blocks,
    })


# ---------------------------------------------------------------------------
# Active config accessor
# ---------------------------------------------------------------------------
#
# There is no existing mechanism carrying ``AgentDiffConfig``/``CaptureConfig``
# into the capture shims (they only reach ``get_active_tracer()``; ``Tracer``
# itself is constructed with no config reference — config is loaded solely by
# CLI commands today). Rather than thread a new constructor parameter through
# ``Tracer`` and every ``sampling.py``/``session.py`` call site, this follows
# the same contextvar + module-level get/set pattern already used for the
# active tracer and the SDK-shim marker in ``agentdiff.capture.tracer``.
# Shims call ``get_active_redaction_config()`` at event-build time; callers
# that load a real ``AgentDiffConfig`` (CLI entry points, ``session.record``,
# ``sampling.py``) should call ``set_active_redaction_config`` once up front.
# If nothing was ever set, the default (``mode="standard"``) config applies —
# redaction is default-on.

_active_redaction_config: contextvars.ContextVar["RedactionConfig | None"] = (
    contextvars.ContextVar("agentdiff_active_redaction_config", default=None)
)


def get_active_redaction_config() -> "RedactionConfig":
    """Return the active ``RedactionConfig``, defaulting to standard mode.

    Default-on: if no config was ever installed via
    ``set_active_redaction_config``, callers still get standard-mode
    redaction rather than an unredacted passthrough.
    """
    from agentdiff.config import RedactionConfig

    cfg = _active_redaction_config.get()
    return cfg if cfg is not None else RedactionConfig()


def set_active_redaction_config(cfg: "RedactionConfig | None") -> None:
    """Install (or clear, with ``None``) the active ``RedactionConfig``.

    Intended to be called once per process/session by whatever loads the
    real ``AgentDiffConfig`` (CLI entry points, ``agentdiff.record``,
    ``sampling.py``), mirroring how ``set_sdk_shim_marker`` is used in
    ``agentdiff.capture.tracer``.
    """
    _active_redaction_config.set(cfg)
