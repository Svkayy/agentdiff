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
