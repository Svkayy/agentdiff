from unittest.mock import MagicMock

import pytest
from server.models import Org, Project, SlackConfig, Run
from server import crypto, notify


class _RecordingSlack:
    def __init__(self, token, **kw):
        self.posted = []

    def post_payload(self, channel, message):
        self.posted.append((channel, message))
        from agentdiff.incident.delivery import DeliveryResult
        return DeliveryResult(ok=True, integration="slack")


class _FailingSlack:
    def __init__(self, token, **kw):
        pass

    def post_payload(self, channel, message):
        raise RuntimeError("slack exploded")


@pytest.mark.asyncio(loop_scope="session")
async def test_slack_posts_on_fail(session, monkeypatch):
    org = Org(name="A")
    project = Project(org=org, name="p")
    session.add(
        SlackConfig(
            project=project,
            channel_id="C1",
            bot_token_encrypted=crypto.encrypt("xoxb-t"),
            enabled=True,
        )
    )
    run = Run(
        project=project,
        idempotency_key="i",
        baseline_ref="m",
        candidate_ref="w",
        tier="hermetic",
        config={},
        status="done",
        verdict="fail",
    )
    session.add(run)
    await session.commit()

    rec = _RecordingSlack("x")
    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: rec)

    findings = [
        {
            "test_case_id": "tc1",
            "title": "Fact Checker invocation changed",
            "verdict": "fail",
            "metric": "invocation_rate",
            "impact_summary": "fired 100% -> 0%",
            "cause_path": "a.py",
            "cause_rule": "code_change",
            "cause_hunk": None,
            "explanation": None,
        }
    ]
    await notify.maybe_post_slack(session, run, findings, "fail")
    assert len(rec.posted) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_slack_failure_is_swallowed(session, monkeypatch):
    org = Org(name="A")
    project = Project(org=org, name="p")
    session.add(
        SlackConfig(
            project=project,
            channel_id="C1",
            bot_token_encrypted=crypto.encrypt("xoxb-t"),
            enabled=True,
        )
    )
    run = Run(
        project=project,
        idempotency_key="i2",
        baseline_ref="m",
        candidate_ref="w",
        tier="hermetic",
        config={},
        status="done",
        verdict="fail",
    )
    session.add(run)
    await session.commit()

    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: _FailingSlack(token))
    # Must not raise.
    await notify.maybe_post_slack(session, run, [], "fail")


@pytest.mark.asyncio(loop_scope="session")
async def test_malformed_finding_dict_is_swallowed(session, monkeypatch):
    org = Org(name="A")
    project = Project(org=org, name="p")
    session.add(
        SlackConfig(
            project=project,
            channel_id="C1",
            bot_token_encrypted=crypto.encrypt("xoxb-t"),
            enabled=True,
        )
    )
    run = Run(
        project=project,
        idempotency_key="i3",
        baseline_ref="m",
        candidate_ref="w",
        tier="hermetic",
        config={},
        status="done",
        verdict="fail",
    )
    session.add(run)
    await session.commit()

    rec = _RecordingSlack("x")
    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: rec)

    # A malformed finding dict should trigger ValidationError inside the try block,
    # be swallowed, and never reach the SlackClient post.
    await notify.maybe_post_slack(session, run, [{"bogus": "not a valid finding"}], "fail")
    assert rec.posted == [], "SlackClient should not be reached when finding validation fails"


# ── Webhook-first delivery tests ──────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_webhook_first_delivery(session, monkeypatch):
    """When webhook_url_encrypted is set, notify uses the webhook — not SlackClient."""
    org = Org(name="wh-org")
    project = Project(org=org, name="wh-proj")
    session.add(
        SlackConfig(
            project=project,
            channel_id="C99",
            bot_token_encrypted=crypto.encrypt("xoxb-wh"),
            webhook_url_encrypted=crypto.encrypt("https://hooks.slack.com/test"),
            enabled=True,
        )
    )
    run = Run(
        project=project,
        idempotency_key="wh1",
        baseline_ref="m",
        candidate_ref="w",
        tier="hermetic",
        config={},
        status="done",
        verdict="fail",
    )
    session.add(run)
    await session.commit()

    webhook_calls: list[tuple[str, dict]] = []
    slack_client_called = False

    def fake_webhook_post(url: str, json: dict, timeout: int):
        webhook_calls.append((url, json))
        mock = MagicMock()
        mock.is_success = True
        mock.status_code = 200
        return mock

    def fake_slack_client(token, **kw):
        nonlocal slack_client_called
        slack_client_called = True
        return _RecordingSlack(token)

    monkeypatch.setattr(notify, "webhook_post_fn", fake_webhook_post)
    monkeypatch.setattr(notify, "SlackClient", fake_slack_client)

    findings = [
        {
            "test_case_id": "tc1",
            "title": "Fact Checker changed",
            "verdict": "fail",
            "metric": "invocation_rate",
            "impact_summary": "dropped 100%->0%",
            "cause_path": "a.py",
            "cause_rule": "code_change",
            "cause_hunk": None,
            "explanation": None,
        }
    ]
    await notify.maybe_post_slack(session, run, findings, "fail")

    assert len(webhook_calls) == 1, "webhook should be called exactly once"
    called_url, called_payload = webhook_calls[0]
    assert called_url == "https://hooks.slack.com/test"
    assert "text" in called_payload or "attachments" in called_payload
    assert not slack_client_called, "SlackClient must NOT be called when webhook is set"


@pytest.mark.asyncio(loop_scope="session")
async def test_webhook_failure_is_swallowed(session, monkeypatch):
    """A webhook POST failure should be swallowed (degrade), not propagate."""
    org = Org(name="wh-fail-org")
    project = Project(org=org, name="wh-fail-proj")
    session.add(
        SlackConfig(
            project=project,
            channel_id="C88",
            bot_token_encrypted=crypto.encrypt("xoxb-wf"),
            webhook_url_encrypted=crypto.encrypt("https://hooks.slack.com/fail"),
            enabled=True,
        )
    )
    run = Run(
        project=project,
        idempotency_key="wh2",
        baseline_ref="m",
        candidate_ref="w",
        tier="hermetic",
        config={},
        status="done",
        verdict="warn",
    )
    session.add(run)
    await session.commit()

    def failing_webhook(url: str, json: dict, timeout: int):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(notify, "webhook_post_fn", failing_webhook)

    # Must not raise.
    await notify.maybe_post_slack(session, run, [], "warn")


@pytest.mark.asyncio(loop_scope="session")
async def test_bot_token_fallback_when_no_webhook(session, monkeypatch):
    """When webhook_url_encrypted is None, the bot-token path is still used."""
    org = Org(name="bt-fallback-org")
    project = Project(org=org, name="bt-fallback-proj")
    session.add(
        SlackConfig(
            project=project,
            channel_id="C11",
            bot_token_encrypted=crypto.encrypt("xoxb-fallback"),
            webhook_url_encrypted=None,
            enabled=True,
        )
    )
    run = Run(
        project=project,
        idempotency_key="wh3",
        baseline_ref="m",
        candidate_ref="w",
        tier="hermetic",
        config={},
        status="done",
        verdict="fail",
    )
    session.add(run)
    await session.commit()

    rec = _RecordingSlack("x")
    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: rec)

    findings = [
        {
            "test_case_id": "tc2",
            "title": "Drift detected",
            "verdict": "fail",
            "metric": "invocation_rate",
            "impact_summary": "anomaly",
            "cause_path": None,
            "cause_rule": None,
            "cause_hunk": None,
            "explanation": None,
        }
    ]
    await notify.maybe_post_slack(session, run, findings, "fail")
    assert len(rec.posted) == 1, "bot-token path should have posted once"
