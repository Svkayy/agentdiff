import pytest
from collector import uploader


def test_build_payload_shapes_sides():
    baseline = [{"test_case_id": "tc1", "version": "baseline", "events": []}]
    candidate = [{"test_case_id": "tc1", "version": "candidate", "events": []}]
    payload = uploader.build_payload(
        "idem-1", "origin/main", "working", "hermetic", {"agents": []},
        attribution={"attributions": []}, baseline_trajs=baseline, candidate_trajs=candidate,
    )
    sides = {t["side"] for t in payload["trajectories"]}
    assert sides == {"baseline", "candidate"}
    assert payload["idempotency_key"] == "idem-1"
    assert payload["attribution"] == {"attributions": []}
    # Strengthen: check all top-level fields match inputs
    assert payload["baseline_ref"] == "origin/main"
    assert payload["candidate_ref"] == "working"
    assert payload["tier"] == "hermetic"
    assert payload["config"] == {"agents": []}
    # Each trajectory item propagates test_case_id and payload is the source dict
    traj_by_side = {t["side"]: t for t in payload["trajectories"]}
    assert traj_by_side["baseline"]["test_case_id"] == "tc1"
    assert traj_by_side["baseline"]["payload"] == baseline[0]
    assert traj_by_side["candidate"]["test_case_id"] == "tc1"
    assert traj_by_side["candidate"]["payload"] == candidate[0]


def test_build_payload_attribution_none():
    """attribution=None is passed through as None in the payload."""
    baseline = [{"test_case_id": "tc2", "version": "baseline", "events": []}]
    candidate = [{"test_case_id": "tc2", "version": "candidate", "events": []}]
    payload = uploader.build_payload(
        "idem-2", "v1.0", "v1.1", "live", {"agents": ["a"]},
        attribution=None, baseline_trajs=baseline, candidate_trajs=candidate,
    )
    assert payload["attribution"] is None


def test_upload_posts_with_bearer():
    calls = []

    def fake_post(url, json, headers):
        calls.append((url, json, headers))

        class R:
            status_code = 202

            def json(self):
                return {"run_id": "r1", "status": "pending"}

        return R()

    out = uploader.upload("https://api.test", "adk_key", {"trajectories": []}, post_fn=fake_post)
    assert out["run_id"] == "r1"
    assert calls[0][0] == "https://api.test/v1/runs"
    assert calls[0][2]["Authorization"] == "Bearer adk_key"


def test_upload_raises_on_error_status():
    """A post_fn returning status_code=400 must raise RuntimeError."""

    def fake_post_400(url, json, headers):
        class R:
            status_code = 400

            def json(self):
                return {}

        return R()

    with pytest.raises(RuntimeError):
        uploader.upload("https://api.test", "adk_key", {"trajectories": []}, post_fn=fake_post_400)
