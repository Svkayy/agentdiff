"""Day 6: Markdown report rendering."""
from agentdiff.compare import (
    AgentInvocationDelta, ComparisonResult, TestCaseComparison, ToolUsageDelta,
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
                behavioral_overlap=0.5,
            )
        ],
    )


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


def test_report_handles_empty_test_case():
    cmp = ComparisonResult(
        overall_verdict="pass",
        test_case_comparisons=[TestCaseComparison(test_case_id="empty", overall_verdict="pass")],
    )
    md = render_report(cmp, [], {"timestamp": "t"})
    assert "No agents or tools observed" in md
