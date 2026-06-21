"""Day 7: causal attribution — manifest diff, rules, and end-to-end engine."""
import shutil
import subprocess
from uuid import uuid4

import pytest

from agentdiff.attribution import engine as attribution_engine
from agentdiff.attribution.manifest import AgentManifest
from agentdiff.attribution.manifest_diff import diff_manifests
from agentdiff.attribution.rules import apply_rules
from agentdiff.capture.events import CallSite, CanonicalLLMCall, LLMRequestEvent
from agentdiff.compare import compare_all
from agentdiff.structure.structure_yaml import AgentEntry, StructureDoc, ToolEntry
from agentdiff.trajectory import Trajectory, TrajectorySet


# ---------------------------------------------------------------------------
# manifest_diff
# ---------------------------------------------------------------------------

def _manifest(prompt_hash, code_hash, model, tools=()):
    return AgentManifest(
        agent_name="Research",
        function="research_agent",
        code_file="agent.py",
        code_hash=code_hash,
        prompt_files=["prompts/research.txt"],
        prompt_content_hash=prompt_hash,
        model_params={"model": model, "sampling_params": {}, "tools": list(tools)},
    )


def test_diff_detects_prompt_change():
    b = {"research_agent": _manifest("hashA", "codeA", "m")}
    c = {"research_agent": _manifest("hashB", "codeA", "m")}
    d = diff_manifests(b, c)["research_agent"]
    assert d.prompt_changed is True
    assert d.code_changed is False
    assert d.model_params_changed is False


def test_diff_detects_code_and_model_and_tools():
    b = {"research_agent": _manifest("h", "codeA", "claude-3", tools=["search"])}
    c = {"research_agent": _manifest("h", "codeB", "claude-4", tools=["search", "calc"])}
    d = diff_manifests(b, c)["research_agent"]
    assert d.code_changed is True
    assert d.model_params_changed is True
    assert d.tools_changed is True
    assert set(d.tools_after) == {"search", "calc"}


# ---------------------------------------------------------------------------
# rules
# ---------------------------------------------------------------------------

STRUCT = StructureDoc(
    agents=[AgentEntry(name="Research", function="research_agent", file="agent.py", line=1)],
    tools=[ToolEntry(name="search", function="web_search", file="tools.py", line=1)],
)


def test_rule_direct_prompt_change_targets_prompt_file():
    d = diff_manifests(
        {"research_agent": _manifest("A", "c", "m")},
        {"research_agent": _manifest("B", "c", "m")},
    )["research_agent"]
    git_diff = {"prompts/research.txt": "@@ -1 +1 @@\n-old\n+new\n"}
    attrs = apply_rules(d, git_diff, STRUCT)
    assert attrs[0].rule == "direct_prompt_change"
    assert attrs[0].target_path == "prompts/research.txt"
    assert attrs[0].weight == 0.9
    assert attrs[0].hunk is not None


def test_rule_code_change():
    d = diff_manifests(
        {"research_agent": _manifest("h", "codeA", "m")},
        {"research_agent": _manifest("h", "codeB", "m")},
    )["research_agent"]
    git_diff = {"agent.py": "@@ -2 +2 @@\n-x\n+y\n"}
    attrs = apply_rules(d, git_diff, STRUCT)
    assert any(a.rule == "code_change" and a.target_path == "agent.py" for a in attrs)


def test_rule_tool_schema_change_targets_tool_file():
    d = diff_manifests(
        {"research_agent": _manifest("h", "c", "m", tools=["search"])},
        {"research_agent": _manifest("h", "c", "m", tools=["search", "calc"])},
    )["research_agent"]
    git_diff = {"tools.py": "@@ -1 +1 @@\n+def calc(): ...\n"}
    attrs = apply_rules(d, git_diff, STRUCT)
    assert any(a.rule == "tool_schema_change" and a.target_path == "tools.py" for a in attrs)


def test_rule_reachable_fallback_when_nothing_direct():
    # No manifest change, nothing provably reachable → blind heuristic (0.2).
    d = diff_manifests(
        {"research_agent": _manifest("h", "c", "m")},
        {"research_agent": _manifest("h", "c", "m")},
    )["research_agent"]
    git_diff = {"utils.py": "@@ -1 +1 @@\n-a\n+b\n"}
    attrs = apply_rules(d, git_diff, STRUCT)
    assert len(attrs) == 1
    assert attrs[0].rule == "reachable_change"
    assert attrs[0].weight == 0.2


def test_rule_reachable_prefers_reachable_changed_file():
    d = diff_manifests(
        {"research_agent": _manifest("h", "c", "m")},
        {"research_agent": _manifest("h", "c", "m")},
    )["research_agent"]
    git_diff = {"helper.py": "@@ -1 +1 @@\n-a\n+b\n", "unrelated.py": "@@ -1 +1 @@\n-x\n+y\n"}
    # helper.py is statically reachable from the agent; unrelated.py is not.
    attrs = apply_rules(d, git_diff, STRUCT, reachable_changed=["helper.py"])
    assert len(attrs) == 1
    assert attrs[0].rule == "reachable_change"
    assert attrs[0].target_path == "helper.py"
    assert attrs[0].weight == 0.35


# ---------------------------------------------------------------------------
# engine end-to-end against a real git repo
# ---------------------------------------------------------------------------

pytestmark_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _agent_traj(tag, prompt, fires=True):
    events = []
    if fires:
        events.append(
            LLMRequestEvent(
                call_id=uuid4(),
                canonical=CanonicalLLMCall(
                    provider="anthropic", model="claude-x",
                    system=prompt, sampling_params={"temperature": 0.5},
                ),
                captured_by="sdk_shim",
                callsite=CallSite(file="agent.py", function="research_agent", line=4),
                inferred_agent="Research",
            )
        )
    return Trajectory(test_case_id="tc1", version_tag=tag, input={}, events=events)


@pytestmark_git
def test_engine_attributes_prompt_change_end_to_end(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    baseline_prompt = "You are a helpful baseline assistant"
    candidate_prompt = "You are a helpful candidate assistant"

    (project / "agent.py").write_text(
        "import anthropic\n"
        f'PROMPT = "{baseline_prompt}"\n'
        "def research_agent(query):\n"
        "    client = anthropic.Anthropic()\n"
        "    return client.messages.create(model='claude-x', system=PROMPT, messages=[])\n"
    )
    _git(["init"], project)
    _git(["config", "user.email", "t@t.com"], project)
    _git(["config", "user.name", "t"], project)
    _git(["add", "-A"], project)
    _git(["commit", "-m", "baseline"], project)

    # Candidate (working tree): change the prompt only.
    (project / "agent.py").write_text(
        (project / "agent.py").read_text().replace(baseline_prompt, candidate_prompt)
    )

    structure = StructureDoc(
        agents=[AgentEntry(name="Research", function="research_agent", file="agent.py", line=3)],
    )

    # 20 baseline (all fire) vs 20 candidate (14 fire) → rate 1.0 → 0.70, a
    # statistically significant drop, so the delta triggers attribution.
    baseline = [_agent_traj("baseline", baseline_prompt) for _ in range(20)]
    candidate = [_agent_traj("candidate", candidate_prompt) for _ in range(14)]
    candidate += [_agent_traj("candidate", candidate_prompt, fires=False) for _ in range(6)]

    b_set = TrajectorySet(version_tag="baseline", trajectories=baseline)
    c_set = TrajectorySet(version_tag="candidate", trajectories=candidate)
    comparison = compare_all(b_set, c_set, structure, ["tc1"])

    result = attribution_engine.attribute(
        comparison=comparison,
        structure=structure,
        baseline_trajectories=baseline,
        candidate_trajectories=candidate,
        repo_root=project,
        baseline_ref="HEAD",
        candidate_ref=None,
        llm_client=None,
    )

    assert len(result.attributions) == 1
    ba = result.attributions[0]
    assert ba.agent_name == "Research"
    assert ba.verdict == "warn"
    assert ba.primary is not None
    assert ba.primary.rule == "direct_prompt_change"
    assert ba.primary.target_path == "agent.py"
    assert "candidate" in ba.primary.hunk
