"""Monte-Carlo validation of AgentDiff's behavioral-regression detector.

Measures, on synthetic trajectories with KNOWN ground truth:
  - False-positive rate (Type I): baseline and candidate drawn from the SAME
    invocation-rate process — the detector should flag a regression <= ~5% of the
    time (the significance gate is alpha = 0.05).
  - Detection power: candidate drawn from a DIFFERENT process (a real regression) —
    fraction of the time the detector catches it.

Run: python benchmarks/bench_detector.py
"""
import random
from uuid import uuid4

from agentdiff.capture.events import CallSite, CanonicalLLMCall, LLMRequestEvent
from agentdiff.compare import compare_test_case
from agentdiff.structure.structure_yaml import AgentEntry, StructureDoc
from agentdiff.trajectory import Trajectory

STRUCT = StructureDoc(agents=[AgentEntry(name="A", function="a", file="a.py", line=1)])
TRIALS = 2000
N = 20  # samples per side (AgentDiff's default)


def _traj(tag: str, fired: bool) -> Trajectory:
    events = []
    if fired:
        events.append(
            LLMRequestEvent(
                call_id=uuid4(),
                canonical=CanonicalLLMCall(provider="anthropic"),
                captured_by="sdk_shim",
                callsite=CallSite(file="a.py", function="a", line=1),
                inferred_agent="A",
            )
        )
    return Trajectory(test_case_id="tc", version_tag=tag, input={}, events=events)


def _flagged(p_b: float, p_c: float, n: int, rng: random.Random) -> bool:
    b = [_traj("baseline", rng.random() < p_b) for _ in range(n)]
    c = [_traj("candidate", rng.random() < p_c) for _ in range(n)]
    return compare_test_case("tc", b, c, STRUCT).overall_verdict != "pass"


def main() -> None:
    rng = random.Random(42)

    # --- False-positive rate: identical processes (no real regression) ---
    for p in (0.5, 0.8):
        flags = sum(_flagged(p, p, N, rng) for _ in range(TRIALS))
        print(f"FPR  | rate {p:.2f} → {p:.2f} | flagged {flags}/{TRIALS} = {flags / TRIALS:.1%}")

    # --- Detection power: real regressions of varying magnitude ---
    for p_b, p_c in ((0.9, 0.5), (0.9, 0.6), (1.0, 0.7), (0.8, 0.4)):
        hits = sum(_flagged(p_b, p_c, N, rng) for _ in range(TRIALS))
        print(f"POWER| rate {p_b:.2f} → {p_c:.2f} | detected {hits}/{TRIALS} = {hits / TRIALS:.1%}")


if __name__ == "__main__":
    main()
