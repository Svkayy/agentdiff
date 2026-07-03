"""Generic webhook delivery for tools AgentDiff does not natively own yet."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable

from agentdiff.incident.delivery import DeliveryResult
from agentdiff.incident.findings import IncidentSummary

WebhookPostFn = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]


class WebhookClient:
    def __init__(self, *, post_fn: WebhookPostFn | None = None):
        self.post_fn = post_fn or _urllib_post

    def post_summary(
        self,
        url: str,
        summary: IncidentSummary,
        *,
        artifacts: dict[str, str] | None = None,
    ) -> DeliveryResult:
        payload = {
            "source": "agentdiff",
            "verdict": summary.verdict,
            "warnings": summary.warnings,
            "findings": [f.model_dump() for f in summary.findings],
            "artifacts": artifacts or {},
        }
        try:
            data = self.post_fn(url, payload, {"Content-Type": "application/json"})
            return DeliveryResult(ok=True, integration="webhook", url=str(data.get("url") or url))
        except Exception as exc:  # noqa: BLE001 - delivery degrades, verdict does not
            return DeliveryResult(ok=False, integration="webhook", error=str(exc))


def _urllib_post(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"webhook HTTP {exc.code}") from exc
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc
