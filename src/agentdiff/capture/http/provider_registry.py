import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ProviderPattern:
    name: str
    url_re: re.Pattern = field(compare=False)


_PATTERNS: list[ProviderPattern] = [
    ProviderPattern("anthropic", re.compile(r"^https://api\.anthropic\.com/v1/messages")),
    ProviderPattern("openai_chat", re.compile(r"^https://api\.openai\.com/v1/chat/completions")),
    ProviderPattern("openai_responses", re.compile(r"^https://api\.openai\.com/v1/responses")),
    ProviderPattern(
        "gemini",
        re.compile(
            r"^https://generativelanguage\.googleapis\.com/v1beta/models/[^/]+:(generateContent|streamGenerateContent)"
        ),
    ),
    ProviderPattern("mistral", re.compile(r"^https://api\.mistral\.ai/v1/chat/completions")),
    ProviderPattern(
        "bedrock",
        re.compile(
            # invoke, invoke-with-response-stream, converse, converse-stream
            r"^https://bedrock-runtime\.[^.]+\.amazonaws\.com/model/[^/]+/(invoke|converse)"
        ),
    ),
    ProviderPattern(
        "azure_openai",
        re.compile(
            r"^https://[^.]+\.openai\.azure\.com/openai/deployments/[^/]+/chat/completions"
        ),
    ),
    ProviderPattern("cohere", re.compile(r"^https://api\.cohere\.(com|ai)/v[12]/chat")),
]


def register(pattern: ProviderPattern) -> None:
    """Add a custom provider pattern. Patterns registered later take priority."""
    _PATTERNS.append(pattern)


_LOADED_CUSTOM_NAMES: set[str] = set()


def load_custom_providers(project_root: Path | str) -> int:
    """Register custom patterns from ``<project_root>/.agentdiff/providers.yaml``.

    Schema:
        providers:
          - name: my_provider
            url_pattern: "^https://api\\\\.myprovider\\\\.com/v1/chat"

    Returns the number of patterns newly registered. Idempotent per provider
    name (loading twice in one process won't duplicate a pattern). Best-effort:
    a malformed file or bad regex is skipped, never raised.
    """
    path = Path(project_root) / ".agentdiff" / "providers.yaml"
    if not path.exists():
        return 0
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return 0

    added = 0
    for entry in (data.get("providers") or []):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        pattern = entry.get("url_pattern")
        if not name or not pattern or name in _LOADED_CUSTOM_NAMES:
            continue
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            logger.warning(
                "Skipping custom provider %r in %s: invalid url_pattern %r (%s)",
                name, path, pattern, exc,
            )
            continue
        register(ProviderPattern(name=name, url_re=compiled))
        _LOADED_CUSTOM_NAMES.add(name)
        added += 1
    return added


def match_provider(url: str) -> str:
    """Return the provider name for a URL, or 'unknown'."""
    for p in reversed(_PATTERNS):  # later registrations win
        if p.url_re.match(url):
            return p.name
    return "unknown"
