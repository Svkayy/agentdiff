"""Tiny in-process Prometheus counter registry.

Deliberately dependency-free: we expose a handful of counters as Prometheus
text (`/metrics`) without pulling in `prometheus_client`.  Counters are process
-local — with multiple API replicas a scrape sees one replica's view, which is
fine for the operational signals we surface (request volume, runs processed,
drift checks, quota rejections).  For fleet-wide totals, scrape each replica.
"""
from __future__ import annotations

import threading

_HELP = {
    "agentdiff_requests_total": "Total HTTP requests handled, by path/method/status.",
    "agentdiff_runs_processed_total": "Total runs processed by the worker.",
    "agentdiff_drift_checks_total": "Total drift checks executed.",
    "agentdiff_quota_rejections_total": "Total ingest requests rejected for quota.",
}

# Counters that carry no labels (single scalar series).
_UNLABELLED = {
    "agentdiff_runs_processed_total",
    "agentdiff_drift_checks_total",
    "agentdiff_quota_rejections_total",
}


class _Registry:
    """Thread-safe counter store keyed by (name, sorted-label-tuple)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # {name: {label_key_tuple: value}}
        self._counters: dict[str, dict[tuple[tuple[str, str], ...], float]] = {}

    def inc(self, name: str, amount: float = 1.0, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        with self._lock:
            series = self._counters.setdefault(name, {})
            series[key] = series.get(key, 0.0) + amount

    def value(self, name: str, **labels: str) -> float:
        key = tuple(sorted(labels.items()))
        with self._lock:
            return self._counters.get(name, {}).get(key, 0.0)

    def reset(self) -> None:
        """Clear all counters (test helper)."""
        with self._lock:
            self._counters.clear()

    def render(self) -> str:
        """Render all counters as Prometheus exposition text."""
        lines: list[str] = []
        with self._lock:
            # Ensure the four canonical metrics always appear, even at zero, so
            # scrapers have a stable schema on a cold process.
            names = set(self._counters) | set(_HELP)
            for name in sorted(names):
                help_text = _HELP.get(name, "")
                lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} counter")
                series = self._counters.get(name, {})
                if not series and name in _UNLABELLED:
                    lines.append(f"{name} 0")
                    continue
                if not series:
                    # Labelled metric with no observations yet — emit nothing
                    # beyond HELP/TYPE (Prometheus tolerates this).
                    continue
                for label_key, value in sorted(series.items()):
                    if label_key:
                        label_str = ",".join(
                            f'{k}="{_escape(v)}"' for k, v in label_key
                        )
                        lines.append(f"{name}{{{label_str}}} {_fmt(value)}")
                    else:
                        lines.append(f"{name} {_fmt(value)}")
        return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _fmt(value: float) -> str:
    return str(int(value)) if value == int(value) else repr(value)


# Process-global registry.
METRICS = _Registry()
