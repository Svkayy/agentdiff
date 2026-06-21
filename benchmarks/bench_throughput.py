"""Throughput + capture-overhead microbenchmarks (single core, in-process).

Measures:
  - Capture path: Tracer open → record events → flush (serialize + write JSONL),
    reported as trajectories/sec and per-event overhead.
  - Storage load: trajectories parsed/sec from JSONL.
  - Comparison engine: trajectories/sec through compare_all (incl. significance tests).

Run: python benchmarks/bench_throughput.py
"""
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from agentdiff.capture.events import (
    CallSite, CanonicalLLMCall, LLMRequestEvent, LLMResponseEvent, LocalToolInvokedEvent,
)
from agentdiff.capture.tracer import Tracer
from agentdiff.compare import compare_all
from agentdiff.storage import load_trajectory_set
from agentdiff.structure.structure_yaml import AgentEntry, StructureDoc
from agentdiff.trajectory import Trajectory, TrajectorySet

STRUCT = StructureDoc(agents=[AgentEntry(name="A", function="a", file="a.py", line=1)])


def _canonical():
    return CanonicalLLMCall(
        provider="anthropic", model="claude-3-5-sonnet", system="sys",
        messages=[{"role": "user", "content": "hello world"}],
        response_text="hi there", usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )


def bench_capture(n_traj=5000):
    """Open a Tracer, record 4 events, flush to JSONL — n_traj times."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "t.jsonl"
        cs = CallSite(file="a.py", function="a", line=1)
        t0 = time.perf_counter()
        for _ in range(n_traj):
            with Tracer("tc", "baseline", {"q": "x"}, out) as tr:
                cid = uuid4()
                tr.record(LLMRequestEvent(call_id=cid, canonical=_canonical(),
                                          captured_by="sdk_shim", callsite=cs, inferred_agent="A"))
                tr.record(LLMResponseEvent(call_id=cid, canonical=_canonical(),
                                           captured_by="sdk_shim", latency_ms=12))
                tr.record(LocalToolInvokedEvent(call_id=cid, tool_name="search", callsite=cs))
                tr.record(LLMRequestEvent(call_id=uuid4(), canonical=_canonical(),
                                          captured_by="sdk_shim", callsite=cs, inferred_agent="A"))
                tr.set_final_output("done")
        dt = time.perf_counter() - t0
    rate = n_traj / dt
    print(f"capture  | {n_traj} trajectories (4 events each) in {dt:.2f}s "
          f"→ {rate:,.0f} traj/s, {dt / n_traj * 1e6:,.0f} µs/traj, "
          f"{dt / (n_traj * 4) * 1e6:,.1f} µs/event")


def bench_load(n_traj=5000):
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "t.jsonl"
        cs = CallSite(file="a.py", function="a", line=1)
        for _ in range(n_traj):
            with Tracer("tc", "baseline", {}, out) as tr:
                tr.record(LLMRequestEvent(call_id=uuid4(), canonical=_canonical(),
                                          captured_by="sdk_shim", callsite=cs, inferred_agent="A"))
        t0 = time.perf_counter()
        ts = load_trajectory_set(out, "baseline")
        dt = time.perf_counter() - t0
    print(f"load     | {len(ts.trajectories)} trajectories parsed in {dt:.2f}s "
          f"→ {len(ts.trajectories) / dt:,.0f} traj/s")


def bench_compare(per_side=2000):
    cs = CallSite(file="a.py", function="a", line=1)

    def traj(tag, fire):
        ev = [LLMRequestEvent(call_id=uuid4(), canonical=_canonical(),
                              captured_by="sdk_shim", callsite=cs, inferred_agent="A")] if fire else []
        return Trajectory(test_case_id="tc", version_tag=tag, input={}, events=ev)

    b = TrajectorySet(version_tag="baseline", trajectories=[traj("baseline", True) for _ in range(per_side)])
    c = TrajectorySet(version_tag="candidate",
                      trajectories=[traj("candidate", i % 2 == 0) for i in range(per_side)])
    t0 = time.perf_counter()
    compare_all(b, c, STRUCT, ["tc"])
    dt = time.perf_counter() - t0
    print(f"compare  | {2 * per_side} trajectories compared (incl. significance) in {dt * 1e3:.1f}ms "
          f"→ {2 * per_side / dt:,.0f} traj/s")


if __name__ == "__main__":
    bench_capture()
    bench_load()
    bench_compare()
