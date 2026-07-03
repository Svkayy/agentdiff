"""Tests for notify enrichment (A1-A4) and recovery (A5)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from agentdiff.capture.events import CallSite, CanonicalLLMCall, LLMRequestEvent
from agentdiff.incident.delivery import DeliveryResult
from agentdiff.structure.structure_yaml import AgentEntry, StructureDoc
from agentdiff.trajectory import Trajectory as EngineTrajectory

from server import crypto, notify
from server.models import Org, Project, Run, SlackConfig, Trajectory
from server.worker import process_run

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

STRUCTURE = StructureDoc(
    agents=[AgentEntry(name="Fact Checker", function="fact_checker", file="agents.py", line=10)]
)
CONFIG = STRUCTURE.model_dump()


def _payload_traj(tc_id: str, tag: str, fires: bool) -> dict:
    cid = uuid4()
    events = []
    if fires:
        events.append(
            LLMRequestEvent(
                call_id=cid,
                canonical=CanonicalLLMCall(provider="anthropic"),
                captured_by="sdk_shim",
                callsite=CallSite(file="agents.py", function="fact_checker", line=10),
                inferred_agent="Fact Checker",
            )
        )
    t = EngineTrajectory(test_case_id=tc_id, version_tag=tag, input={}, events=events)
    return t.model_dump(mode="json")


def _factory(session):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


class _RecordingSlack:
    def __init__(self, token, **kw):
        self.posted: list[tuple] = []

    def post_payload(self, channel, message):
        self.posted.append((channel, message))
        return DeliveryResult(ok=True, integration="slack")


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


# ---------------------------------------------------------------------------
# A1 — Context block: project name, kind, refs, sample counts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_enriched_payload_context_block(session, monkeypatch):
    """Enriched payload's context block contains project name, kind, refs, n=8 vs 8."""
    org = Org(name=f"enrich-org-{uuid4()}")
    project = Project(org=org, name=f"my-project-{uuid4()}")
    session.add(org)
    session.add(project)

    run = Run(
        project=project,
        idempotency_key=f"enrich-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat/abc",
        tier="hermetic",
        kind="ci",
        config=CONFIG,
        status="done",
        verdict="fail",
    )
    session.add(run)
    await session.flush()

    # 8 baseline + 8 candidate trajectories
    for _ in range(8):
        session.add(Trajectory(run_id=run.id, side="baseline", test_case_id="tc1", payload={}))
    for _ in range(8):
        session.add(Trajectory(run_id=run.id, side="candidate", test_case_id="tc1", payload={}))

    sc = SlackConfig(
        project=project,
        channel_id="C-enrich",
        bot_token_encrypted=crypto.encrypt("xoxb-test"),
        enabled=True,
    )
    session.add(sc)
    await session.commit()

    captured: list[dict] = []

    class _Cap:
        def __init__(self, token, **kw):
            pass

        def post_payload(self, channel, message):
            captured.append(message)
            return DeliveryResult(ok=True, integration="slack")

    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: _Cap(token))

    await notify.maybe_post_slack(session, run, [_VALID_FINDING], "fail")

    assert len(captured) == 1
    payload = captured[0]
    blocks = payload["attachments"][0]["blocks"]

    # Find the context block
    ctx_blocks = [b for b in blocks if b.get("type") == "context"]
    assert ctx_blocks, "Expected a context block in enriched payload"
    ctx_text = ctx_blocks[0]["elements"][0]["text"]

    assert project.name in ctx_text, f"Project name missing from context: {ctx_text!r}"
    assert "CI" in ctx_text, f"Kind badge missing: {ctx_text!r}"
    assert "main" in ctx_text, f"baseline_ref missing: {ctx_text!r}"
    assert "feat/abc" in ctx_text, f"candidate_ref missing: {ctx_text!r}"
    assert "n=8 vs 8" in ctx_text, f"Sample counts missing: {ctx_text!r}"


# ---------------------------------------------------------------------------
# A2 — Cause hunk: present + truncated at 12 lines; explanation quoted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_hunk_block_present_and_truncated(session, monkeypatch):
    """A 30-line hunk is truncated to 12 lines + '…' in the Slack section block."""
    org = Org(name=f"hunk-org-{uuid4()}")
    project = Project(org=org, name=f"hunk-proj-{uuid4()}")
    session.add(org)
    session.add(project)

    thirty_line_hunk = "\n".join(f"line {i}" for i in range(30))
    finding_with_hunk = {
        **_VALID_FINDING,
        "cause_hunk": thirty_line_hunk,
        "explanation": "The agent was removed from the pipeline.",
    }

    run = Run(
        project=project,
        idempotency_key=f"hunk-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat",
        tier="hermetic",
        kind="ci",
        config=CONFIG,
        status="done",
        verdict="fail",
    )
    sc = SlackConfig(
        project=project,
        channel_id="C-hunk",
        bot_token_encrypted=crypto.encrypt("xoxb-hunk"),
        enabled=True,
    )
    session.add_all([run, sc])
    await session.commit()

    captured: list[dict] = []

    class _Cap:
        def __init__(self, token, **kw):
            pass

        def post_payload(self, channel, message):
            captured.append(message)
            return DeliveryResult(ok=True, integration="slack")

    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: _Cap(token))

    await notify.maybe_post_slack(session, run, [finding_with_hunk], "fail")

    assert len(captured) == 1
    blocks = captured[0]["attachments"][0]["blocks"]
    section_texts = [
        b["text"]["text"] for b in blocks if b.get("type") == "section"
    ]

    # Find hunk block (code fence)
    hunk_sections = [t for t in section_texts if "```" in t]
    assert hunk_sections, f"No hunk code-fence block found. Sections: {section_texts}"
    hunk_text = hunk_sections[0]

    # Should be truncated to 12 lines
    inner = hunk_text.replace("```", "")
    lines_in_block = [ln for ln in inner.split("\n") if ln]
    # 12 lines + "…" at the end
    assert "…" in hunk_text, "Truncation marker '…' missing from hunk block"
    assert len(lines_in_block) <= 13, f"Too many lines in hunk block: {len(lines_in_block)}"

    # Explanation should be quoted
    quoted = [t for t in section_texts if t.startswith(">")]
    assert quoted, f"Explanation quote block missing. Sections: {section_texts}"
    assert "The agent was removed" in quoted[0]


# ---------------------------------------------------------------------------
# A3 — Deep link button present with correct URL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_view_in_agentdiff_button(session, monkeypatch):
    """Actions block contains 'View in AgentDiff' button pointing to dashboard_url/runs/{id}."""
    org = Org(name=f"btn-org-{uuid4()}")
    project = Project(org=org, name=f"btn-proj-{uuid4()}")
    session.add(org)
    session.add(project)

    run = Run(
        project=project,
        idempotency_key=f"btn-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat",
        tier="hermetic",
        kind="ci",
        config=CONFIG,
        status="done",
        verdict="fail",
    )
    sc = SlackConfig(
        project=project,
        channel_id="C-btn",
        bot_token_encrypted=crypto.encrypt("xoxb-btn"),
        enabled=True,
    )
    session.add_all([run, sc])
    await session.commit()

    captured: list[dict] = []

    class _Cap:
        def __init__(self, token, **kw):
            pass

        def post_payload(self, channel, message):
            captured.append(message)
            return DeliveryResult(ok=True, integration="slack")

    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: _Cap(token))

    from server.config import get_settings
    dashboard_url = get_settings().dashboard_url

    await notify.maybe_post_slack(session, run, [_VALID_FINDING], "fail")

    assert len(captured) == 1
    blocks = captured[0]["attachments"][0]["blocks"]
    actions = [b for b in blocks if b.get("type") == "actions"]
    assert actions, "No actions block found"

    buttons = actions[-1].get("elements", [])
    view_buttons = [e for e in buttons if "View in AgentDiff" in e.get("text", {}).get("text", "")]
    assert view_buttons, f"'View in AgentDiff' button not found. Elements: {buttons}"
    assert view_buttons[0]["url"] == f"{dashboard_url}/runs/{run.id}"


# ---------------------------------------------------------------------------
# A4 — Drift extra_context renders window line
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_drift_extra_context_window_line(session, monkeypatch):
    """Drift extra_context renders '24h window · n=<nb> vs <nc>' in context block."""
    org = Org(name=f"drift-enrich-org-{uuid4()}")
    project = Project(org=org, name=f"drift-enrich-proj-{uuid4()}")
    session.add(org)
    session.add(project)

    run = Run(
        project=project,
        idempotency_key=f"drift-enrich-{uuid4()}",
        baseline_ref="window[-2880m,-1440m)",
        candidate_ref="window[-1440m,now)",
        tier="live",
        kind="drift",
        config=CONFIG,
        status="done",
        verdict="warn",
    )
    sc = SlackConfig(
        project=project,
        channel_id="C-drift",
        bot_token_encrypted=crypto.encrypt("xoxb-drift"),
        enabled=True,
    )
    session.add_all([run, sc])
    await session.commit()

    captured: list[dict] = []

    class _Cap:
        def __init__(self, token, **kw):
            pass

        def post_payload(self, channel, message):
            captured.append(message)
            return DeliveryResult(ok=True, integration="slack")

    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: _Cap(token))

    await notify.maybe_post_slack(
        session,
        run,
        [_VALID_FINDING],
        "warn",
        extra_context={"window_minutes": 1440, "baseline_samples": 15, "candidate_samples": 12},
    )

    assert len(captured) == 1
    blocks = captured[0]["attachments"][0]["blocks"]
    ctx_blocks = [b for b in blocks if b.get("type") == "context"]
    assert ctx_blocks, "No context block in drift payload"
    ctx_text = ctx_blocks[0]["elements"][0]["text"]

    assert "LIVE DRIFT" in ctx_text, f"Kind badge missing: {ctx_text!r}"
    assert "24h" in ctx_text, f"Window duration missing: {ctx_text!r}"
    assert "n=15 vs 12" in ctx_text, f"Sample counts missing: {ctx_text!r}"


# ---------------------------------------------------------------------------
# A5 — Recovery notification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_recovery_posted_after_fail(session, monkeypatch):
    """pass after fail → recovery payload posted (green color, 'recovered' in header)."""
    org = Org(name=f"rec-org-{uuid4()}")
    project = Project(org=org, name=f"rec-proj-{uuid4()}")
    session.add_all([org, project])

    sc = SlackConfig(
        project=project,
        channel_id="C-rec",
        bot_token_encrypted=crypto.encrypt("xoxb-rec"),
        enabled=True,
    )
    session.add(sc)
    await session.commit()

    # Previous CI run (verdict=fail), created one minute ago
    prev_run = Run(
        project=project,
        idempotency_key=f"rec-prev-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat",
        tier="hermetic",
        kind="ci",
        config=CONFIG,
        status="done",
        verdict="fail",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    session.add(prev_run)
    await session.commit()

    # Current run (verdict=pass), seeded with 8 vs 8 trajectories
    run = Run(
        project=project,
        idempotency_key=f"rec-curr-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat2",
        tier="hermetic",
        kind="ci",
        config=CONFIG,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    session.add(run)
    await session.flush()

    for _ in range(8):
        session.add(Trajectory(run_id=run.id, side="baseline", test_case_id="tc1",
                               payload=_payload_traj("tc1", "baseline", True)))
    for _ in range(8):
        session.add(Trajectory(run_id=run.id, side="candidate", test_case_id="tc1",
                               payload=_payload_traj("tc1", "candidate", True)))

    await session.commit()

    captured: list[dict] = []

    class _Cap:
        def __init__(self, token, **kw):
            pass

        def post_payload(self, channel, message):
            captured.append(message)
            return DeliveryResult(ok=True, integration="slack")

    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: _Cap(token))

    await process_run({"session_factory": _factory(session)}, str(run.id))

    await session.refresh(run)

    if run.verdict == "pass":
        # Find recovery post (the one with green color)
        recovery_posts = [
            m for m in captured
            if m.get("attachments") and m["attachments"][0].get("color") == "#3FB27F"
        ]
        assert recovery_posts, (
            f"Expected a recovery post (green color). Got {len(captured)} posts. "
            f"Verdicts: {[m.get('text','') for m in captured]}"
        )
        header_text = recovery_posts[0]["attachments"][0]["blocks"][0]["text"]["text"]
        assert "recovered" in header_text.lower(), f"'recovered' not in header: {header_text!r}"


@pytest.mark.asyncio(loop_scope="session")
async def test_no_recovery_on_pass_after_pass(session, monkeypatch):
    """pass after pass → NO recovery post."""
    org = Org(name=f"nrec-org-{uuid4()}")
    project = Project(org=org, name=f"nrec-proj-{uuid4()}")
    session.add_all([org, project])

    sc = SlackConfig(
        project=project,
        channel_id="C-nrec",
        bot_token_encrypted=crypto.encrypt("xoxb-nrec"),
        enabled=True,
    )
    session.add(sc)
    await session.commit()

    prev_run = Run(
        project=project,
        idempotency_key=f"nrec-prev-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat",
        tier="hermetic",
        kind="ci",
        config=CONFIG,
        status="done",
        verdict="pass",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    session.add(prev_run)
    await session.commit()

    run = Run(
        project=project,
        idempotency_key=f"nrec-curr-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat2",
        tier="hermetic",
        kind="ci",
        config=CONFIG,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    session.add(run)
    await session.flush()

    for _ in range(8):
        session.add(Trajectory(run_id=run.id, side="baseline", test_case_id="tc1",
                               payload=_payload_traj("tc1", "baseline", True)))
    for _ in range(8):
        session.add(Trajectory(run_id=run.id, side="candidate", test_case_id="tc1",
                               payload=_payload_traj("tc1", "candidate", True)))
    await session.commit()

    captured: list[dict] = []

    class _Cap:
        def __init__(self, token, **kw):
            pass

        def post_payload(self, channel, message):
            captured.append(message)
            return DeliveryResult(ok=True, integration="slack")

    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: _Cap(token))

    await process_run({"session_factory": _factory(session)}, str(run.id))

    await session.refresh(run)
    recovery_posts = [
        m for m in captured
        if m.get("attachments") and m["attachments"][0].get("color") == "#3FB27F"
    ]
    assert not recovery_posts, f"Unexpected recovery post on pass-after-pass: {recovery_posts}"


@pytest.mark.asyncio(loop_scope="session")
async def test_recovery_delivery_failure_swallowed(session, monkeypatch):
    """Recovery delivery failure is swallowed — does not propagate."""
    org = Org(name=f"recfail-org-{uuid4()}")
    project = Project(org=org, name=f"recfail-proj-{uuid4()}")
    session.add_all([org, project])

    sc = SlackConfig(
        project=project,
        channel_id="C-recfail",
        bot_token_encrypted=crypto.encrypt("xoxb-rf"),
        enabled=True,
    )
    session.add(sc)
    await session.commit()

    prev_run = Run(
        project=project,
        idempotency_key=f"rf-prev-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat",
        tier="hermetic",
        kind="ci",
        config=CONFIG,
        status="done",
        verdict="fail",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    session.add(prev_run)
    await session.commit()

    run = Run(
        project=project,
        idempotency_key=f"rf-curr-{uuid4()}",
        baseline_ref="main",
        candidate_ref="feat2",
        tier="hermetic",
        kind="ci",
        config=CONFIG,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    session.add(run)
    await session.flush()

    for _ in range(8):
        session.add(Trajectory(run_id=run.id, side="baseline", test_case_id="tc1",
                               payload=_payload_traj("tc1", "baseline", True)))
    for _ in range(8):
        session.add(Trajectory(run_id=run.id, side="candidate", test_case_id="tc1",
                               payload=_payload_traj("tc1", "candidate", True)))
    await session.commit()

    class _FailSlack:
        def __init__(self, token, **kw):
            pass

        def post_payload(self, channel, message):
            raise RuntimeError("slack dead")

    monkeypatch.setattr(notify, "SlackClient", lambda token, **k: _FailSlack(token))

    # Must not raise
    await process_run({"session_factory": _factory(session)}, str(run.id))


# ---------------------------------------------------------------------------
# A5 — Hunk truncation unit test (fast, no DB)
# ---------------------------------------------------------------------------


def test_hunk_truncation_at_12_lines():
    """_truncate_hunk cuts at 12 lines and appends '…'."""
    hunk = "\n".join(f"line {i}" for i in range(30))
    result = notify._truncate_hunk(hunk)
    assert result.endswith("…"), "Expected truncation marker"
    lines = result.replace("…", "").splitlines()
    assert len(lines) == 12, f"Expected 12 lines, got {len(lines)}"


def test_hunk_no_truncation_for_short_hunk():
    """_truncate_hunk leaves short hunks untouched."""
    hunk = "\n".join(f"line {i}" for i in range(5))
    result = notify._truncate_hunk(hunk)
    assert "…" not in result
    assert result == hunk
