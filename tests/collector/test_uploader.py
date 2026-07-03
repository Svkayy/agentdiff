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
