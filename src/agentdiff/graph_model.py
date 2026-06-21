"""Before/after agent-graph model for the dashboard (Slice 1).

Turns the artifacts a ``compare`` run already persists (the ComparisonResult plus
the optional attribution) together with the captured trajectories into a
renderable node/edge model:

    nodes = agents (one per structure agent, from the comparison) ∪ tools
    edges = agent → tool   (from tool events' ``inferred_agent``)

Agent→subagent edges are deferred: the parent agent identity is not persisted on
events (each event carries only its own ``inferred_agent``), so reconstructing the
call hierarchy needs the capture-time agent map, which lives in a later slice.

An agent that STOPPED firing (baseline rate > 0, candidate rate 0) is still
emitted as a node, marked ``stopped``, so the renderer can light it red. That
disappearance is the signal the product exists to surface, so it must never be
dropped. Nodes and edges are the UNION across baseline and candidate.

Known upstream limitation (NOT handled here): if the baseline and candidate refs
resolve agent names differently (e.g. a renamed function, or a structure.yaml
present on one side only), the comparison itself mislabels the agent. That is a
compare/sampling concern upstream of this rendering layer.
"""
from pydantic import BaseModel, Field

from agentdiff.compare import ComparisonResult, Verdict
from agentdiff.trajectory import TrajectorySet

_SEVERITY = {"pass": 0, "warn": 1, "fail": 2}


class GraphNode(BaseModel):
    id: str
    label: str
    kind: str  # "agent" | "tool"
    baseline_rate: float = 0.0  # agents: invocation rate; tools: avg calls/trajectory
    candidate_rate: float = 0.0
    verdict: Verdict = "pass"
    fired: bool = True  # fired in the candidate
    stopped: bool = False  # fired in baseline, not in candidate — the red signal
    cause_file: str | None = None
    hunk: str | None = None
    explanation: str | None = None


class GraphEdge(BaseModel):
    source: str
    target: str


class AgentGraph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    overall_verdict: Verdict = "pass"
    has_change: bool = False


def _worst(a: Verdict, b: Verdict) -> Verdict:
    return a if _SEVERITY[a] >= _SEVERITY[b] else b


def _finalize_fire_state(node: GraphNode) -> None:
    node.fired = node.candidate_rate > 0.0
    node.stopped = node.baseline_rate > 0.0 and node.candidate_rate == 0.0


def build(
    comparison: ComparisonResult | dict | None,
    attribution: dict | None,
    baseline: TrajectorySet,
    candidate: TrajectorySet,
) -> AgentGraph:
    """Build the before/after graph.

    ``comparison`` may be a ``ComparisonResult`` or its serialized dict (as
    returned by ``storage.read_artifact``). ``attribution`` is the serialized
    attribution dict, or ``None`` when attribution was skipped (e.g. no API key).
    """
    if comparison is None:
        comp = ComparisonResult()
    elif isinstance(comparison, ComparisonResult):
        comp = comparison
    else:
        comp = ComparisonResult.model_validate(comparison)

    # Agent nodes — aggregate each agent across test cases (one node per agent).
    agents: dict[str, GraphNode] = {}
    for tc in comp.test_case_comparisons:
        for d in tc.agent_invocation_deltas:
            node = agents.get(d.agent_name)
            if node is None:
                agents[d.agent_name] = GraphNode(
                    id=f"agent:{d.agent_name}",
                    label=d.agent_name,
                    kind="agent",
                    baseline_rate=d.baseline_rate,
                    candidate_rate=d.candidate_rate,
                    verdict=d.verdict,
                )
            else:
                node.baseline_rate = max(node.baseline_rate, d.baseline_rate)
                node.candidate_rate = max(node.candidate_rate, d.candidate_rate)
                node.verdict = _worst(node.verdict, d.verdict)
    for node in agents.values():
        _finalize_fire_state(node)

    # Tool nodes — same aggregation over tool-usage deltas.
    tools: dict[str, GraphNode] = {}
    for tc in comp.test_case_comparisons:
        for td in tc.tool_usage_deltas:
            node = tools.get(td.tool_name)
            if node is None:
                tools[td.tool_name] = GraphNode(
                    id=f"tool:{td.tool_name}",
                    label=td.tool_name,
                    kind="tool",
                    baseline_rate=td.baseline_avg,
                    candidate_rate=td.candidate_avg,
                    verdict=td.verdict,
                )
            else:
                node.baseline_rate = max(node.baseline_rate, td.baseline_avg)
                node.candidate_rate = max(node.candidate_rate, td.candidate_avg)
                node.verdict = _worst(node.verdict, td.verdict)
    for node in tools.values():
        _finalize_fire_state(node)

    # Attach attribution (cause file + hunk + explanation) to agent nodes.
    if attribution:
        for att in attribution.get("attributions", []):
            node = agents.get(att.get("agent_name"))
            if node is None:
                continue
            primary = att.get("primary") or {}
            node.cause_file = primary.get("target_path")
            node.hunk = primary.get("hunk")
            node.explanation = att.get("explanation")

    # Agent→tool edges: union across both sides; keep only edges between nodes.
    agent_names = set(agents)
    tool_names = set(tools)
    edges: set[tuple[str, str]] = set()
    for tset in (baseline, candidate):
        for traj in tset.trajectories:
            for ev in traj.tool_calls():
                agent = getattr(ev, "inferred_agent", None)
                tool = getattr(ev, "tool_name", None)
                if agent in agent_names and tool in tool_names:
                    edges.add((f"agent:{agent}", f"tool:{tool}"))

    nodes = list(agents.values()) + list(tools.values())
    has_change = any(n.verdict != "pass" or n.stopped for n in nodes)
    return AgentGraph(
        nodes=nodes,
        edges=[GraphEdge(source=s, target=t) for s, t in sorted(edges)],
        overall_verdict=comp.overall_verdict,
        has_change=has_change,
    )
