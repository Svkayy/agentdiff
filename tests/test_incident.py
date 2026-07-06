from agentdiff.attribution.engine import AttributionResult, BehavioralAttribution
from agentdiff.attribution.rules import Attribution
from agentdiff.compare import (
    AgentInvocationDelta, ComparisonResult, RunMetricDelta, TestCaseComparison,
)
from agentdiff.incident.findings import IncidentContext, build_incident_summary
from agentdiff.incident.github import AGENTDIFF_COMMENT_MARKER, GitHubClient, infer_pr_number
from agentdiff.incident.renderers import (
    render_postmortem,
    render_pr_check,
    render_slack_blocks,
    render_slack_payload,
)
from agentdiff.incident.slack import SlackClient
from agentdiff.incident.webhook import WebhookClient


def _comparison(verdict="fail"):
    return ComparisonResult(
        overall_verdict=verdict,
        test_case_comparisons=[
            TestCaseComparison(
                test_case_id="tc1",
                overall_verdict=verdict,
                agent_invocation_deltas=[
                    AgentInvocationDelta(
                        agent_name="Fact Checker",
                        function="fact_checker",
                        baseline_rate=1.0,
                        candidate_rate=0.0,
                        delta=-1.0,
                        baseline_count=5,
                        candidate_count=0,
                        baseline_total=5,
                        candidate_total=5,
                        p_value=0.01,
                        significant=True,
                        verdict=verdict,
                    )
                ],
            )
        ],
    )


def test_incident_summary_merges_attribution_once():
    attribution = AttributionResult(
        attributions=[
            BehavioralAttribution(
                test_case_id="tc1",
                agent_name="Fact Checker",
                function="fact_checker",
                metric="invocation_rate",
                delta_summary="invocation rate 100% -> 0%",
                verdict="fail",
                primary=Attribution(
                    rule="code_change",
                    target_path="agents/fact_checker.py",
                    hunk="@@ -1 +1 @@",
                    weight=0.9,
                    reason="agent code changed",
                ),
            )
        ]
    )

    summary = build_incident_summary(_comparison(), attribution)

    assert summary.verdict == "fail"
    # One test case → exactly one aggregated finding
    assert len(summary.findings) == 1
    assert summary.findings[0].cause_path == "agents/fact_checker.py"
    assert "100%" in summary.findings[0].impact_summary
    assert summary.findings[0].test_cases_affected == 1
    assert summary.findings[0].test_cases_total == 1


def test_low_confidence_attribution_renders_heuristic_label():
    attribution = AttributionResult(
        attributions=[
            BehavioralAttribution(
                test_case_id="tc1",
                agent_name="Fact Checker",
                function="fact_checker",
                metric="invocation_rate",
                delta_summary="invocation rate 100% -> 0%",
                verdict="fail",
                primary=Attribution(
                    rule="reachable_change",
                    target_path="utils.py",
                    hunk="@@ -1 +1 @@",
                    weight=0.2,
                    confidence="low",
                    reason="low confidence heuristic reason",
                ),
            )
        ]
    )
    summary = build_incident_summary(_comparison(), attribution)
    assert summary.findings[0].cause_confidence == "low"

    pr_check = render_pr_check(summary)
    postmortem = render_postmortem(summary)
    blocks = render_slack_blocks(summary)

    assert "(low-confidence heuristic)" in pr_check
    assert "(low-confidence heuristic)" in postmortem
    assert any(
        "(low-confidence heuristic)" in b.get("text", {}).get("text", "")
        for b in blocks
        if b.get("type") == "section"
    )


def test_run_metric_delta_produces_finding():
    comparison = ComparisonResult(
        overall_verdict="fail",
        test_case_comparisons=[
            TestCaseComparison(
                test_case_id="tc1",
                overall_verdict="fail",
                run_metric_deltas=[
                    RunMetricDelta(
                        metric="latency_ms", baseline_mean=500.0, candidate_mean=8000.0,
                        delta=7500.0, p_value=0.01, adjusted_p_value=0.01,
                        significant=True, low_power=False, verdict="fail",
                    ),
                    RunMetricDelta(
                        metric="total_tokens", baseline_mean=100.0, candidate_mean=105.0,
                        delta=5.0, p_value=0.9, adjusted_p_value=0.9,
                        significant=False, low_power=False, verdict="pass",
                    ),
                ],
            )
        ],
    )
    summary = build_incident_summary(comparison)
    metrics = {f.metric for f in summary.findings}
    assert "latency_ms" in metrics
    assert "total_tokens" not in metrics  # pass verdicts don't surface as findings
    latency_finding = next(f for f in summary.findings if f.metric == "latency_ms")
    assert latency_finding.verdict == "fail"
    assert "500.00" in latency_finding.impact_summary
    assert "8000.00" in latency_finding.impact_summary


def test_run_metric_finding_averages_means_over_all_test_cases_not_just_failing():
    # Two test cases both compute latency_ms: tc1 has a big FAIL shift, tc2 is
    # a passing test case (verdict "pass", no shift). The displayed finding's
    # baseline/candidate means must be the average across BOTH test cases —
    # not just the failing one — while the worst verdict (fail) still gates.
    comparison = ComparisonResult(
        overall_verdict="fail",
        test_case_comparisons=[
            TestCaseComparison(
                test_case_id="tc1",
                overall_verdict="fail",
                run_metric_deltas=[
                    RunMetricDelta(
                        metric="latency_ms", baseline_mean=500.0, candidate_mean=8000.0,
                        delta=7500.0, p_value=0.01, adjusted_p_value=0.01,
                        significant=True, low_power=False, verdict="fail",
                    ),
                ],
            ),
            TestCaseComparison(
                test_case_id="tc2",
                overall_verdict="pass",
                run_metric_deltas=[
                    RunMetricDelta(
                        metric="latency_ms", baseline_mean=300.0, candidate_mean=300.0,
                        delta=0.0, p_value=1.0, adjusted_p_value=1.0,
                        significant=False, low_power=False, verdict="pass",
                    ),
                ],
            ),
        ],
    )
    summary = build_incident_summary(comparison)
    latency_finding = next(f for f in summary.findings if f.metric == "latency_ms")

    # Worst verdict across test cases still governs whether/how this gates.
    assert latency_finding.verdict == "fail"

    # Means must be pooled across BOTH test cases (500+300)/2=400, (8000+300)/2=4150 —
    # not just the failing test case's 500.0/8000.0.
    assert "400.00" in latency_finding.impact_summary
    assert "4150.00" in latency_finding.impact_summary
    assert "500.00" not in latency_finding.impact_summary
    assert "8000.00" not in latency_finding.impact_summary


def test_empty_input_is_warn_not_pass():
    summary = build_incident_summary(
        ComparisonResult(overall_verdict="pass", test_case_comparisons=[]),
        input_count=0,
    )
    assert summary.verdict == "warn"
    assert "0 inputs" in summary.warnings[0]


def test_renderers_share_same_summary():
    summary = build_incident_summary(_comparison())

    assert "AgentDiff CI Gate: CHANGE" in render_pr_check(summary)
    assert "Postmortem Draft" in render_postmortem(summary)
    blocks = render_slack_blocks(summary, detail_url="https://example.com/report")
    assert blocks[0]["type"] == "header"
    assert blocks[-1]["type"] == "actions"


def test_slack_failure_degrades_to_result():
    def fake_post(url, payload, headers):
        return {"ok": False, "error": "invalid_auth"}

    client = SlackClient("xoxb-bad", post_fn=fake_post, max_retries=0)
    result = client.post_blocks("C123", [{"type": "section", "text": {"type": "mrkdwn", "text": "hi"}}])

    assert result.ok is False
    assert result.error == "invalid_auth"


def test_webhook_posts_structured_payload():
    calls = []

    def fake_post(url, payload, headers):
        calls.append((url, payload, headers))
        return {"url": "https://hooks.example/1"}

    summary = build_incident_summary(_comparison())
    result = WebhookClient(post_fn=fake_post).post_summary(
        "https://hooks.example/agentdiff",
        summary,
        artifacts={"summary_path": "/tmp/agentdiff-ci.md"},
    )

    assert result.ok is True
    assert calls[0][1]["source"] == "agentdiff"
    assert calls[0][1]["verdict"] == "fail"
    assert calls[0][1]["artifacts"]["summary_path"].endswith("agentdiff-ci.md")


def test_github_upserts_existing_pr_comment():
    calls = []

    def fake_request(method, url, payload, headers):
        calls.append((method, url, payload))
        if method == "GET":
            return [
                {
                    "url": "https://api.github.com/repos/o/r/issues/comments/10",
                    "body": f"{AGENTDIFF_COMMENT_MARKER}\nold",
                }
            ]
        return {"html_url": "https://github.com/o/r/pull/1#issuecomment-10"}

    result = GitHubClient("ghs_test", request_fn=fake_request).upsert_pr_comment(
        repository="o/r",
        pr_number=1,
        body="# AgentDiff CI Gate: CHANGE\n",
    )

    assert result.ok is True
    assert calls[0][0] == "GET"
    assert calls[1][0] == "PATCH"
    assert AGENTDIFF_COMMENT_MARKER in calls[1][2]["body"]


def test_github_delivery_failure_degrades():
    def fake_request(method, url, payload, headers):
        raise RuntimeError("github HTTP 403")

    result = GitHubClient("ghs_bad", request_fn=fake_request).upsert_pr_comment(
        repository="o/r",
        pr_number=1,
        body="body",
    )

    assert result.ok is False
    assert result.integration == "github"
    assert "403" in result.error


def test_infer_pr_number_from_github_event(tmp_path):
    event = tmp_path / "event.json"
    event.write_text('{"pull_request": {"number": 42}}', encoding="utf-8")
    assert infer_pr_number(event) == 42


def _context():
    return IncidentContext(
        repository="acme/support-bot",
        pr_number=482,
        baseline_ref="origin/main",
        candidate_ref="working",
        tier="hermetic",
        run_url="https://github.com/acme/support-bot/actions/runs/99",
    )


def test_incident_context_builds_pr_url():
    assert _context().pr_url() == "https://github.com/acme/support-bot/pull/482"
    assert IncidentContext(repository="acme/support-bot").pr_url() is None
    assert IncidentContext(pr_number=1).pr_url() is None


def test_slack_blocks_carry_repo_pr_and_tier_context():
    summary = build_incident_summary(_comparison())
    blocks = render_slack_blocks(summary, context=_context(), detail_url="https://example.com/r")

    context_block = blocks[1]
    assert context_block["type"] == "context"
    line = context_block["elements"][0]["text"]
    assert "acme/support-bot" in line
    assert "PR #482" in line
    assert "hermetic tier" in line

    actions = blocks[-1]
    urls = [el["url"] for el in actions["elements"]]
    assert "https://example.com/r" in urls
    assert "https://github.com/acme/support-bot/pull/482" in urls
    assert "https://github.com/acme/support-bot/actions/runs/99" in urls


def test_slack_payload_colors_by_verdict():
    fail_payload = render_slack_payload(build_incident_summary(_comparison()))
    assert fail_payload["attachments"][0]["color"] == "#FF4D2E"
    assert "Fact Checker invocation changed" in fail_payload["text"]

    pass_payload = render_slack_payload(
        build_incident_summary(
            ComparisonResult(overall_verdict="pass", test_case_comparisons=[]),
            input_count=3,
        )
    )
    assert pass_payload["attachments"][0]["color"] == "#3FB27F"

    warn_payload = render_slack_payload(
        build_incident_summary(
            ComparisonResult(overall_verdict="pass", test_case_comparisons=[]),
            input_count=0,
        )
    )
    assert warn_payload["attachments"][0]["color"] == "#E8A33D"


def test_slack_headline_same_agent_two_test_cases_aggregates_to_one():
    """Same agent change across 2 test cases → ONE aggregated finding, not two."""
    comparison = _comparison()
    extra = comparison.test_case_comparisons[0].model_copy(
        update={"test_case_id": "tc2"}
    )
    comparison = ComparisonResult(
        overall_verdict="fail",
        test_case_comparisons=[comparison.test_case_comparisons[0], extra],
    )
    summary = build_incident_summary(comparison)
    # Aggregated: ONE finding covers both test cases
    assert len(summary.findings) == 1
    assert summary.findings[0].test_cases_affected == 2
    assert summary.findings[0].test_cases_total == 2
    assert "2 of 2 inputs" in summary.findings[0].impact_summary
    # Headline names the single finding, not "2 behavioral changes"
    blocks = render_slack_blocks(summary)
    assert "Fact Checker invocation changed" in blocks[0]["text"]["text"]
    # No "Also affected" section when there is only one aggregated finding
    listed = [b for b in blocks if b["type"] == "section" and "Also affected" in b["text"]["text"]]
    assert len(listed) == 0


def test_slack_headline_counts_multiple_distinct_agent_findings():
    """Two DIFFERENT agents changing → two findings → '2 behavioral changes detected'."""
    from agentdiff.compare import AgentInvocationDelta, TestCaseComparison

    comparison = ComparisonResult(
        overall_verdict="fail",
        test_case_comparisons=[
            TestCaseComparison(
                test_case_id="tc1",
                overall_verdict="fail",
                agent_invocation_deltas=[
                    AgentInvocationDelta(
                        agent_name="Fact Checker",
                        function="fact_checker",
                        baseline_rate=1.0,
                        candidate_rate=0.0,
                        delta=-1.0,
                        baseline_count=5,
                        candidate_count=0,
                        baseline_total=5,
                        candidate_total=5,
                        p_value=0.01,
                        significant=True,
                        verdict="fail",
                    ),
                    AgentInvocationDelta(
                        agent_name="Summarizer",
                        function="summarizer",
                        baseline_rate=1.0,
                        candidate_rate=0.0,
                        delta=-1.0,
                        baseline_count=5,
                        candidate_count=0,
                        baseline_total=5,
                        candidate_total=5,
                        p_value=0.01,
                        significant=True,
                        verdict="fail",
                    ),
                ],
            )
        ],
    )
    summary = build_incident_summary(comparison)
    assert len(summary.findings) == 2
    blocks = render_slack_blocks(summary)
    assert "2 behavioral changes detected" in blocks[0]["text"]["text"]
    listed = [b for b in blocks if b["type"] == "section" and "Also affected" in b["text"]["text"]]
    assert len(listed) == 1


def test_slack_post_payload_merges_channel_and_fallback():
    calls = []

    def fake_post(url, payload, headers):
        calls.append(payload)
        return {"ok": True}

    client = SlackClient("xoxb-ok", post_fn=fake_post)
    summary = build_incident_summary(_comparison())
    result = client.post_payload("C123", render_slack_payload(summary, context=_context()))

    assert result.ok is True
    assert calls[0]["channel"] == "C123"
    assert calls[0]["attachments"][0]["color"] == "#FF4D2E"
    assert calls[0]["text"].startswith("AgentDiff CHANGE")


def test_pr_check_and_postmortem_include_context():
    summary = build_incident_summary(_comparison())
    pr_check = render_pr_check(summary, context=_context())
    assert "acme/support-bot" in pr_check
    postmortem = render_postmortem(summary, context=_context())
    assert "**Pull request:** #482" in postmortem
    assert "`origin/main` → `working`" in postmortem
    assert "**Tier:** hermetic" in postmortem
