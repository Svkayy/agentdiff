"""Day 6: Markdown report rendering."""
from agentdiff.compare import (
    AgentInvocationDelta, ComparisonResult, RunMetricDelta, TestCaseComparison, ToolUsageDelta,
)
from agentdiff.output_eval import OutputEvalResult
from agentdiff.report import render_report


def _comparison():
    return ComparisonResult(
        overall_verdict="fail",
        test_case_comparisons=[
            TestCaseComparison(
                test_case_id="tc1",
                overall_verdict="fail",
                agent_invocation_deltas=[
                    AgentInvocationDelta(
                        agent_name="Router", function="route",
                        baseline_rate=1.0, candidate_rate=0.0, delta=-1.0,
                        baseline_count=4, candidate_count=0,
                        baseline_total=4, candidate_total=4, verdict="fail",
                    )
                ],
                tool_usage_deltas=[
                    ToolUsageDelta(
                        tool_name="web_search", baseline_avg=2.0,
                        candidate_avg=1.0, delta=-1.0, verdict="fail",
                    )
                ],
                run_metric_deltas=[
                    RunMetricDelta(
                        metric="latency_ms", baseline_mean=500.0, candidate_mean=8000.0,
                        delta=7500.0, p_value=0.01, adjusted_p_value=0.01,
                        significant=True, low_power=False, verdict="fail",
                    ),
                    RunMetricDelta(
                        metric="total_tokens", baseline_mean=100.0, candidate_mean=100.0,
                        delta=0.0, p_value=1.0, adjusted_p_value=1.0,
                        significant=False, low_power=False, verdict="pass",
                    ),
                    RunMetricDelta(
                        metric="error_rate", baseline_mean=0.0, candidate_mean=0.5,
                        delta=0.5, p_value=0.01, adjusted_p_value=0.01,
                        significant=True, low_power=False, verdict="fail",
                    ),
                ],
                behavioral_overlap=0.5,
            )
        ],
    )


def test_output_eval_table_escapes_pipes_in_skipped_check_reason():
    """A `|` character in a skipped-check reason (or note) must be escaped so
    it doesn't fracture the Markdown table into extra columns."""
    cmp = _comparison()
    evals = [
        OutputEvalResult(
            test_case_id="tc1",
            verdict="pass",
            semantic_similarity=0.99,
            notes=["note with a | pipe"],
            skipped_checks=[
                {"check": "semantic", "reason": "module a|b not installed"},
            ],
        )
    ]
    meta = {"timestamp": "2026-05-31_120000", "baseline_ref": "main",
            "candidate_ref": "working", "samples_per_case": 20}

    md = render_report(cmp, evals, meta)

    row = next(
        line for line in md.splitlines()
        if line.startswith("| `tc1`") and "installed" in line
    )
    # The Output Evaluation Details header declares 8 columns → a
    # well-formed row has exactly 9 "|" once any pipes inside cell content
    # are escaped (`\|`, which doesn't count as a column separator).
    assert row.count("|") - row.count("\\|") == 9
    assert "module a\\|b not installed" in row
    assert "note with a \\| pipe" in row


def test_report_contains_all_sections():
    cmp = _comparison()
    evals = [OutputEvalResult(test_case_id="tc1", verdict="pass", semantic_similarity=0.99)]
    meta = {"timestamp": "2026-05-31_120000", "baseline_ref": "main",
            "candidate_ref": "working", "samples_per_case": 20}

    md = render_report(cmp, evals, meta)

    assert "# AgentDiff Report" in md
    assert "Summary: Traditional Eval vs AgentDiff" in md
    assert "Behavioral Findings" in md
    assert "Causal Attribution" in md
    assert "Reproduction" in md
    # The headline contrast: traditional PASS, behavioral FAIL.
    assert "| `tc1` | PASS | FAIL |" in md
    assert "Router" in md
    assert "web_search" in md
    assert "agentdiff compare --baseline main" in md
    assert "Runtime deltas" in md
    assert "latency_ms" in md
    assert "total_tokens" in md
    assert "error_rate" in md


def test_report_handles_empty_test_case():
    cmp = ComparisonResult(
        overall_verdict="pass",
        test_case_comparisons=[TestCaseComparison(test_case_id="empty", overall_verdict="pass")],
    )
    md = render_report(cmp, [], {"timestamp": "t"})
    assert "No agents or tools observed" in md
