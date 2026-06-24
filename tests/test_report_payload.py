import json
from pathlib import Path
from uuid import uuid4

from agentdiff import report_payload, storage
from agentdiff.compare import (
    AgentInvocationDelta, ComparisonResult, TestCaseComparison, ToolUsageDelta,
)
from agentdiff.capture.events import (
    CallSite, CanonicalLLMCall, LLMRequestEvent, LLMResponseEvent,
)
from agentdiff.trajectory import Trajectory, TrajectorySet

_CALLSITE = CallSite(file="agents/x.py", function="f", line=1)


def _llm_pair(agent, model, text):
    # Mirror real capture: the request event carries inferred_agent; the
    # response event shares the call_id and has no agent of its own.
    cid = uuid4()
    req = LLMRequestEvent(
        sequence=0, call_id=cid,
        canonical=CanonicalLLMCall(provider="openai", model=model,
                                   messages=[{"role": "user", "content": "q"}]),
        captured_by="http_shim", callsite=_CALLSITE, inferred_agent=agent,
    )
    resp = LLMResponseEvent(
        sequence=1, latency_ms=42, call_id=cid,
        canonical=CanonicalLLMCall(provider="openai", model=model,
                                   response_text=text, usage={"input_tokens": 5, "output_tokens": 7}),
        captured_by="http_shim",
    )
    return [req, resp]


def _traj(tag, tcid, agent, model, text):
    return Trajectory(test_case_id=tcid, version_tag=tag, input={"query": "q"},
                      final_output=text, total_tokens=12, total_latency_ms=42,
                      events=_llm_pair(agent, model, text))


def _write_run(tmp_path: Path) -> Path:
    comparison = ComparisonResult(
        overall_verdict="fail",
        test_case_comparisons=[TestCaseComparison(
            test_case_id="basic", overall_verdict="fail", behavioral_overlap=0.5,
            agent_invocation_deltas=[AgentInvocationDelta(
                agent_name="fact_checker", function="fact_checker_agent",
                baseline_rate=1.0, candidate_rate=0.0, delta=-1.0,
                baseline_count=2, candidate_count=0, baseline_total=2, candidate_total=2,
                p_value=0.01, significant=True, verdict="fail")],
            tool_usage_deltas=[ToolUsageDelta(
                tool_name="web_search", baseline_avg=1.0, candidate_avg=2.0, delta=1.0,
                p_value=0.02, significant=True, verdict="fail")],
        )],
    )
    attribution = {"attributions": [{
        "agent_name": "fact_checker", "delta_summary": "stopped firing", "verdict": "fail",
        "primary": {"target_path": "prompts/orchestrator.md", "rule": "prompt_change",
                    "weight": 0.9, "reason": "routing removed", "hunk": "@@ -1 +1 @@\n-route\n+skip"},
        "alternatives": [], "explanation": "The routing line was removed."}]}
    baseline = TrajectorySet(version_tag="baseline",
                             trajectories=[_traj("baseline", "basic", "fact_checker", "llama3.1:8b", "B")])
    candidate = TrajectorySet(version_tag="candidate",
                              trajectories=[_traj("candidate", "basic", "retriever", "llama3.1:8b", "C")])
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    (report_dir / "metadata.json").write_text(json.dumps({
        "baseline_ref": "HEAD", "candidate_ref": "working", "samples_per_case": 2,
        "timestamp": "2026-06-24_120000", "smoke_mode": False,
        "baseline_trajectories": 1, "candidate_trajectories": 1,
        "baseline_failed": 0, "candidate_failed": 0, "max_failure_rate": 0.0,
        "thresholds": {"agent_invocation_rate_warn": 0.2}}))
    storage.write_run_store(report_dir / "agentdiff.sqlite", metadata={"run_id": "r1"},
                            baseline_set=baseline, candidate_set=candidate,
                            comparison=comparison, output_evals=[], attribution=attribution)
    return report_dir


def test_build_assembles_all_sections(tmp_path):
    payload = report_payload.build(_write_run(tmp_path))
    assert payload["meta"]["baseline_ref"] == "HEAD"
    assert payload["runQuality"]["baseline_trajectories"] == 1
    assert payload["graph"]["overall_verdict"] == "fail"
    assert payload["comparison"]["test_case_comparisons"][0]["agent_invocation_deltas"][0]["agent_name"] == "fact_checker"
    assert payload["attribution"]["attributions"][0]["primary"]["target_path"] == "prompts/orchestrator.md"
    tl = payload["trajectories"]["baseline"][0]["timeline"]
    assert tl[0]["kind"] == "llm_request"
    assert tl[0]["inferred_agent"] == "fact_checker"
    assert tl[0]["request_preview"] == "q"
    assert tl[1]["kind"] == "llm_response"
    assert tl[1]["model"] == "llama3.1:8b"
    # response carries no agent of its own; correlated from the request's call_id
    assert tl[1]["inferred_agent"] == "fact_checker"
    assert tl[1]["response_preview"] == "B"


def test_build_tolerates_missing_metadata_and_artifacts(tmp_path):
    # A bare sqlite with no artifacts / no metadata.json still yields a valid shape.
    report_dir = tmp_path / "bare"
    report_dir.mkdir()
    storage.write_run_store(report_dir / "agentdiff.sqlite", metadata={"run_id": "r0"},
                            baseline_set=TrajectorySet(version_tag="baseline", trajectories=[]),
                            candidate_set=TrajectorySet(version_tag="candidate", trajectories=[]))
    payload = report_payload.build(report_dir)
    assert payload["comparison"] is None or payload["comparison"]["test_case_comparisons"] == []
    assert payload["trajectories"] == {"baseline": [], "candidate": []}
    assert "graph" in payload and "meta" in payload
