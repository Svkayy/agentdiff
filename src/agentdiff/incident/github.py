"""GitHub PR delivery for AgentDiff CI findings."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from agentdiff.incident.delivery import DeliveryResult

AGENTDIFF_COMMENT_MARKER = "<!-- agentdiff-ci -->"

GitHubRequestFn = Callable[[str, str, Any | None, dict[str, str]], Any]


class GitHubClient:
    def __init__(self, token: str, *, request_fn: GitHubRequestFn | None = None):
        self.token = token
        self.request_fn = request_fn or _urllib_request

    def upsert_pr_comment(
        self,
        *,
        repository: str,
        pr_number: int,
        body: str,
        marker: str = AGENTDIFF_COMMENT_MARKER,
    ) -> DeliveryResult:
        """Create or update one AgentDiff PR comment.

        Delivery never raises to the CI command; the PR check remains the source
        of truth if GitHub API permissions are missing.
        """
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        comment_body = f"{marker}\n{body}"
        base = f"https://api.github.com/repos/{repository}/issues/{pr_number}/comments"
        try:
            comments = self.request_fn("GET", base, None, headers)
            existing = _find_existing_comment(comments, marker)
            if existing is not None:
                url = str(existing["url"])
                data = self.request_fn("PATCH", url, {"body": comment_body}, headers)
            else:
                data = self.request_fn("POST", base, {"body": comment_body}, headers)
            return DeliveryResult(
                ok=True,
                integration="github",
                url=str(data.get("html_url") or ""),
            )
        except Exception as exc:  # noqa: BLE001 - delivery degrades, verdict does not
            return DeliveryResult(ok=False, integration="github", error=str(exc))


def infer_pr_number(event_path: str | Path | None) -> int | None:
    """Infer a pull request number from GitHub's event JSON, if present."""
    if not event_path:
        return None
    path = Path(event_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    pr = data.get("pull_request")
    if isinstance(pr, dict) and pr.get("number") is not None:
        return int(pr["number"])
    if data.get("number") is not None and "pull_request" in data:
        return int(data["number"])
    return None


def _find_existing_comment(comments: Any, marker: str) -> dict[str, Any] | None:
    if not isinstance(comments, list):
        return None
    for comment in comments:
        if isinstance(comment, dict) and marker in str(comment.get("body") or ""):
            return comment
    return None


def _urllib_request(
    method: str,
    url: str,
    payload: Any | None,
    headers: dict[str, str],
) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"github HTTP {exc.code}") from exc
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc
