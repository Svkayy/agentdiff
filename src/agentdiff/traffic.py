import csv
import hashlib
import json
from pathlib import Path
from typing import Any

_QUERY_KEYS = (
    "query",
    "message",
    "prompt",
    "input",
    "text",
    "content",
    "request",
    "user_query",
    "question",
)


def discover_test_cases(source: Path, *, max_cases: int = 25) -> list[dict[str, Any]]:
    """Infer AgentDiff test cases from JSONL, CSV, or plain-text traffic samples."""
    rows = list(_read_rows(Path(source)))
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        query = _extract_query(row)
        if not query:
            continue
        fingerprint = _fingerprint(query)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        cases.append(
            {
                "id": f"traffic_{len(cases) + 1:03d}_{fingerprint[:8]}",
                "input": _input_payload(row, query),
                "tags": ["traffic", _intent_tag(query)],
            }
        )
        if len(cases) >= max_cases:
            break
    return cases


def _read_rows(source: Path):
    suffix = source.suffix.lower()
    if suffix == ".jsonl":
        with open(source, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
        return
    if suffix == ".json":
        data = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(data, list):
            yield from data
        elif isinstance(data, dict):
            for key in ("events", "requests", "messages", "rows"):
                if isinstance(data.get(key), list):
                    yield from data[key]
                    return
            yield data
        return
    if suffix == ".csv":
        with open(source, newline="", encoding="utf-8") as f:
            yield from csv.DictReader(f)
        return

    with open(source, encoding="utf-8", errors="replace") as f:
        for line in f:
            text = line.strip()
            if text:
                yield {"query": text}


def _extract_query(row: Any) -> str | None:
    if isinstance(row, str):
        return row.strip() or None
    if not isinstance(row, dict):
        return None
    lowered = {str(k).lower(): v for k, v in row.items()}
    for key in _QUERY_KEYS:
        value = lowered.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in lowered.values():
        if isinstance(value, str) and len(value.strip()) >= 12:
            return value.strip()
    return None


def _input_payload(row: Any, query: str) -> dict[str, Any]:
    if isinstance(row, dict):
        payload = {
            str(k): v
            for k, v in row.items()
            if isinstance(v, (str, int, float, bool)) or v is None
        }
        payload.setdefault("query", query)
        return payload
    return {"query": query}


def _fingerprint(text: str) -> str:
    normalized = " ".join(text.lower().split())
    return hashlib.sha1(normalized.encode()).hexdigest()


def _intent_tag(query: str) -> str:
    lower = query.lower()
    buckets = {
        "billing": ("bill", "invoice", "subscription", "refund", "payment"),
        "support": ("help", "issue", "problem", "broken", "error", "can't", "cannot"),
        "pricing": ("price", "pricing", "cost", "plan"),
        "search": ("find", "search", "look up", "where"),
        "creative": ("write", "draft", "compose", "generate"),
    }
    for tag, needles in buckets.items():
        if any(needle in lower for needle in needles):
            return tag
    return "general"
