"""Slack delivery for AgentDiff incident briefs."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from agentdiff.incident.delivery import DeliveryResult


class SlackError(RuntimeError):
    """Base class for Slack delivery failures."""


class SlackAuthError(SlackError):
    """Slack token is missing, invalid, or revoked."""


class SlackChannelError(SlackError):
    """Slack channel is missing, archived, or inaccessible."""


class SlackTransientError(SlackError):
    """Slack returned a retryable error or the network failed."""


PostFn = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]


class SlackClient:
    def __init__(
        self,
        token: str,
        *,
        post_fn: PostFn | None = None,
        max_retries: int = 2,
    ):
        self.token = token
        self.post_fn = post_fn or _urllib_post
        self.max_retries = max_retries

    def post_blocks(self, channel: str, blocks: list[dict[str, Any]]) -> DeliveryResult:
        payload = {"channel": channel, "blocks": blocks, "text": "AgentDiff incident brief"}
        return self._post_payload(payload)

    def post_payload(self, channel: str, message: dict[str, Any]) -> DeliveryResult:
        """Post a full chat.postMessage payload (attachments carry the color bar)."""
        payload = {"channel": channel, **message}
        payload.setdefault("text", "AgentDiff incident brief")
        return self._post_payload(payload)

    def _post_payload(self, payload: dict[str, Any]) -> DeliveryResult:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        try:
            self._post_with_retries(payload, headers)
            return DeliveryResult(ok=True, integration="slack")
        except SlackError as exc:
            return DeliveryResult(ok=False, integration="slack", error=str(exc))

    def _post_with_retries(self, payload: dict[str, Any], headers: dict[str, str]) -> None:
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            try:
                data = self.post_fn("https://slack.com/api/chat.postMessage", payload, headers)
                _raise_for_slack_payload(data)
                return
            except SlackTransientError:
                if attempt == attempts - 1:
                    raise
                time.sleep(0.2 * (attempt + 1))


def _raise_for_slack_payload(data: dict[str, Any]) -> None:
    if data.get("ok") is True:
        return
    error = str(data.get("error") or "unknown_error")
    if error in {"invalid_auth", "not_authed", "token_revoked"}:
        raise SlackAuthError(error)
    if error in {"channel_not_found", "is_archived", "not_in_channel"}:
        raise SlackChannelError(error)
    raise SlackTransientError(error)


def _urllib_post(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise SlackAuthError(f"slack HTTP {exc.code}") from exc
        if exc.code == 429 or exc.code >= 500:
            raise SlackTransientError(f"slack HTTP {exc.code}") from exc
        raise SlackChannelError(f"slack HTTP {exc.code}") from exc
    except OSError as exc:
        raise SlackTransientError(str(exc)) from exc
