from agentdiff import report_payload, storage
from agentdiff.trajectory import TrajectorySet
from tests._sample_run import _write_run


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


def test_build_includes_run_metrics_with_exact_field_names(tmp_path):
    payload = report_payload.build(_write_run(tmp_path))
    run_metrics = payload["comparison"]["test_case_comparisons"][0]["run_metrics"]
    metrics = {rm["metric"] for rm in run_metrics}
    assert metrics == {"latency_ms", "total_tokens", "error_rate"}
    for rm in run_metrics:
        assert set(rm.keys()) == {
            "metric", "baseline_mean", "candidate_mean", "delta",
            "p_value", "adjusted_p_value", "verdict", "low_power",
        }


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
