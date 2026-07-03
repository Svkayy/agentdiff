from __future__ import annotations

from typing import Any, Callable


def build_payload(
    idempotency_key: str,
    baseline_ref: str,
    candidate_ref: str,
    tier: str,
    config: dict[str, Any],
    attribution: dict[str, Any] | None,
    baseline_trajs: list[dict[str, Any]],
    candidate_trajs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the RunUpload payload for the hosted API."""
    trajectories = [
        {"side": "baseline", "test_case_id": t["test_case_id"], "payload": t}
        for t in baseline_trajs
    ] + [
        {"side": "candidate", "test_case_id": t["test_case_id"], "payload": t}
        for t in candidate_trajs
    ]
    return {
        "idempotency_key": idempotency_key,
        "baseline_ref": baseline_ref,
        "candidate_ref": candidate_ref,
        "tier": tier,
        "config": config,
        "attribution": attribution,
        "trajectories": trajectories,
    }


def upload(
    api_url: str,
    api_key: str,
    payload: dict[str, Any],
    *,
    post_fn: Callable | None = None,
) -> dict[str, Any]:
    """POST payload to {api_url}/v1/runs with Bearer auth. Raises RuntimeError on HTTP >= 300."""

    def _default_post(url: str, json: dict, headers: dict):
        import httpx

        return httpx.post(url, json=json, headers=headers, timeout=30)

    post = post_fn or _default_post
    resp = post(
        f"{api_url.rstrip('/')}/v1/runs",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"agentdiff upload failed: HTTP {resp.status_code}")
    return resp.json()
