#!/usr/bin/env python3
"""Seed one demo AgentDiff run into your hosted stack. No LLM keys needed.

Turns the `support_agent.py` story into a real run: baseline (all three
sub-agents fire) vs candidate (the Fact Checker went silent after a "latency
fix"). AgentDiff diffs the two, flags the regression, and attributes it to the
exact file. Open the run in the dashboard to see the Fact Checker node go ember.

Usage (from the repo root, with the venv active):

    export AGENTDIFF_API_URL=http://localhost:8000
    export AGENTDIFF_API_KEY=adk_...        # mint one in the dashboard Setup tab
    python demo/seed_run.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid

from agentdiff.attribution.engine import AttributionResult, BehavioralAttribution
from agentdiff.attribution.rules import Attribution
from agentdiff.capture.events import CallSite, CanonicalLLMCall, LLMRequestEvent
from agentdiff.structure.structure_yaml import AgentEntry, StructureDoc
from agentdiff.trajectory import Trajectory as EngineTrajectory

# (display name, function, file, line)
AGENTS = [
    ("Retriever", "retriever", "agents/retriever.py", 12),
    ("Fact Checker", "fact_checker", "agents/fact_checker.py", 20),
    ("Summarizer", "summarizer", "agents/summarizer.py", 30),
]
REGRESSED = "Fact Checker"      # goes silent on the candidate
SAMPLES = 8                     # per side — enough for a significant delta
TEST_CASE = "capital_of_france"


def _structure() -> dict:
    return StructureDoc(
        agents=[AgentEntry(name=n, function=f, file=fp, line=ln) for n, f, fp, ln in AGENTS]
    ).model_dump()


def _trajectory(tag: str, firing: list[str]) -> dict:
    events = [
        LLMRequestEvent(
            call_id=uuid.uuid4(),
            canonical=CanonicalLLMCall(provider="anthropic"),
            captured_by="sdk_shim",
            callsite=CallSite(file=fp, function=fn, line=ln),
            inferred_agent=name,
        )
        for name, fn, fp, ln in AGENTS
        if name in firing
    ]
    return EngineTrajectory(
        test_case_id=TEST_CASE, version_tag=tag, input={"q": "capital of France?"}, events=events
    ).model_dump(mode="json")


def _attribution() -> dict:
    return AttributionResult(
        attributions=[
            BehavioralAttribution(
                test_case_id=TEST_CASE,
                agent_name=REGRESSED,
                function="fact_checker",
                metric="invocation_rate",
                delta_summary="fired 100% on baseline, 0% on candidate",
                verdict="fail",
                primary=Attribution(
                    rule="code_change",
                    target_path="agents/fact_checker.py",
                    hunk=(
                        "@@ -20,6 +20,7 @@ def fact_checker(draft):\n"
                        "+    return draft  # skip for latency\n"
                        "     return llm_call('fact_checker', ...)"
                    ),
                    weight=0.92,
                    reason="fact_checker body changed: an early return was added before the LLM call",
                ),
                explanation=(
                    "The Fact Checker stopped issuing its LLM call after an early return was "
                    "introduced in agents/fact_checker.py — the answer still returns, but nothing "
                    "is fact-checked."
                ),
            )
        ]
    ).model_dump(mode="json")


def _payload() -> dict:
    all_names = [a[0] for a in AGENTS]
    candidate = [n for n in all_names if n != REGRESSED]
    trajectories = (
        [{"side": "baseline", "test_case_id": TEST_CASE, "payload": _trajectory("baseline", all_names)}
         for _ in range(SAMPLES)]
        + [{"side": "candidate", "test_case_id": TEST_CASE, "payload": _trajectory("candidate", candidate)}
           for _ in range(SAMPLES)]
    )
    return {
        "idempotency_key": f"demo-{uuid.uuid4()}",
        "baseline_ref": "origin/main",
        "candidate_ref": "feat/latency-fix",
        "tier": "hermetic",
        "config": _structure(),
        "attribution": _attribution(),
        "trajectories": trajectories,
    }


def main() -> None:
    api = os.environ.get("AGENTDIFF_API_URL", "http://localhost:8000").rstrip("/")
    key = os.environ.get("AGENTDIFF_API_KEY")
    if not key:
        sys.exit("Set AGENTDIFF_API_KEY first — mint one in the dashboard Setup tab.")

    req = urllib.request.Request(
        f"{api}/v1/runs",
        data=json.dumps(_payload()).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            out = json.load(resp)
    except urllib.error.HTTPError as exc:
        sys.exit(f"Upload failed: HTTP {exc.code} — {exc.read().decode()[:300]}")
    except urllib.error.URLError as exc:
        sys.exit(f"Could not reach {api}. Is the stack up (docker compose up)? {exc.reason}")

    print(f"✓ Run accepted: {out['run_id']} (status: {out['status']})")
    print("  The worker is analyzing it now. In the dashboard, open your project → Runs,")
    print("  then open this run: the Fact Checker node turns ember on the candidate side,")
    print("  with the cause attributed to agents/fact_checker.py.")


if __name__ == "__main__":
    main()
