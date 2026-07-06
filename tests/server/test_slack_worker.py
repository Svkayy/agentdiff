from unittest.mock import MagicMock

import pytest
from server.models import Org, Project, SlackConfig, Run
from server import crypto, notify
from agentdiff.incident.delivery import DeliveryResult


class _RecordingSlack:
    def __init__(self, token, **kw):
        self.posted = []

    def post_payload(self, channel, message):
        self.posted.append((channel, message))
        return DeliveryResult(ok=True, integration="slack")


class _FailingSlack:
    def __init__(self, token, **kw):
        pass

    def post_payload(self, channel, message):
        raise RuntimeError("slack exploded")


class _NotInChannelSlack:
    """Returns ok=False, error=not_in_channel — simulates private-channel bot failure."""

    def __init__(self, token, **kw):
        pass

    def post_payload(self, channel, message):
        return DeliveryResult(ok=False, integration="slack", error="not_in_channel")


_VALID_FINDING = {
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


# ── (a) Bot post succeeds → webhook NOT called ────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_bot_post_succeeds_webhook_not_called(session, monkeypatch):
    """Bot post succeeds (ok=True) → webhook is never called (bot-first)."""
    org = Org(name="bot-first-org")
    project = Project(org=org, name="bot-first-proj")
    session.add(
        SlackConfig(
            project=project,
            channel_id="C1",
            bot_token_encrypted=crypto.encrypt("xoxb-t"),
            webhook_url_encrypted=crypto.encrypt("https://hooks.slack.com/test"),
            enabled=True,
        )
    )
    run = Run(
        project=project,
        idempotency_key="bf1",
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
    webhook_calls: list = []

    def fake_webhook(url, json, timeout):
        webhook_calls.append(url)
        mock = MagicMock()
        mock.is_success = True
        mock.status_code = 200
        return mock

    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: rec)
    monkeypatch.setattr(notify, "webhook_post_fn", fake_webhook)

    await notify.maybe_post_slack(session, run, [_VALID_FINDING], "fail")

    assert len(rec.posted) == 1, "bot SlackClient should post once"
    assert webhook_calls == [], "webhook must NOT be called when bot succeeds"


# ── (b) Bot post fails + webhook configured → webhook IS called (fallback) ────


@pytest.mark.asyncio(loop_scope="session")
async def test_bot_post_fails_webhook_fallback(session, monkeypatch):
    """Bot returns ok=False (e.g. not_in_channel) → webhook fallback is used."""
    org = Org(name="fallback-org")
    project = Project(org=org, name="fallback-proj")
    session.add(
        SlackConfig(
            project=project,
            channel_id="C2",
            bot_token_encrypted=crypto.encrypt("xoxb-priv"),
            webhook_url_encrypted=crypto.encrypt("https://hooks.slack.com/priv"),
            enabled=True,
        )
    )
    run = Run(
        project=project,
        idempotency_key="fb1",
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

    def fake_webhook(url: str, json: dict, timeout: int):
        webhook_calls.append((url, json))
        mock = MagicMock()
        mock.is_success = True
        mock.status_code = 200
        return mock

    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: _NotInChannelSlack(token))
    monkeypatch.setattr(notify, "webhook_post_fn", fake_webhook)

    await notify.maybe_post_slack(session, run, [_VALID_FINDING], "fail")

    assert len(webhook_calls) == 1, "webhook fallback should be called once"
    called_url, called_payload = webhook_calls[0]
    assert called_url == "https://hooks.slack.com/priv"
    assert "text" in called_payload or "attachments" in called_payload


# ── (c) Bot fails + webhook-only effective path → webhook used ────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_webhook_used_when_bot_not_in_channel(session, monkeypatch):
    """Bot configured but raises (not_in_channel) + webhook set → webhook used."""
    org = Org(name="wh-only-org")
    project = Project(org=org, name="wh-only-proj")
    session.add(
        SlackConfig(
            project=project,
            channel_id="C3",
            bot_token_encrypted=crypto.encrypt("xoxb-not-member"),
            webhook_url_encrypted=crypto.encrypt("https://hooks.slack.com/only"),
            enabled=True,
        )
    )
    run = Run(
        project=project,
        idempotency_key="wo1",
        baseline_ref="m",
        candidate_ref="w",
        tier="hermetic",
        config={},
        status="done",
        verdict="warn",
    )
    session.add(run)
    await session.commit()

    webhook_calls: list[str] = []

    def fake_webhook(url: str, json: dict, timeout: int):
        webhook_calls.append(url)
        mock = MagicMock()
        mock.is_success = True
        mock.status_code = 200
        return mock

    # Bot raises → bot_ok stays False → falls through to webhook
    monkeypatch.setattr(notify, "webhook_post_fn", fake_webhook)
    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: _FailingSlack(token))

    await notify.maybe_post_slack(session, run, [_VALID_FINDING], "warn")

    assert len(webhook_calls) == 1, "webhook should be called once when bot fails"
    assert webhook_calls[0] == "https://hooks.slack.com/only"


# ── (d) Both fail → swallowed, no raise ──────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_both_fail_swallowed(session, monkeypatch):
    """Bot raises AND webhook raises → nothing propagates (degrade)."""
    org = Org(name="both-fail-org")
    project = Project(org=org, name="both-fail-proj")
    session.add(
        SlackConfig(
            project=project,
            channel_id="C4",
            bot_token_encrypted=crypto.encrypt("xoxb-fail"),
            webhook_url_encrypted=crypto.encrypt("https://hooks.slack.com/fail"),
            enabled=True,
        )
    )
    run = Run(
        project=project,
        idempotency_key="bf2",
        baseline_ref="m",
        candidate_ref="w",
        tier="hermetic",
        config={},
        status="done",
        verdict="fail",
    )
    session.add(run)
    await session.commit()

    def failing_webhook(url: str, json: dict, timeout: int):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: _FailingSlack(token))
    monkeypatch.setattr(notify, "webhook_post_fn", failing_webhook)

    # Must not raise.
    await notify.maybe_post_slack(session, run, [_VALID_FINDING], "fail")


# ── Keep existing degrade + malformed-finding tests ──────────────────────────


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

    findings = [_VALID_FINDING]
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


# ── Webhook-failure swallow ───────────────────────────────────────────────────


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
    # Bot also fails so the fallback path (webhook) is exercised
    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: _NotInChannelSlack(token))

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
