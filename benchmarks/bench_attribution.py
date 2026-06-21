"""Attribution-accuracy benchmark on controlled regression scenarios.

For each of the 5 change types, build a real git repo, inject ONE known change of
that type in the working tree, feed the engine trajectories exhibiting a behavioral
regression, and check whether the engine's PRIMARY attribution names the right rule
and the right file. Reports overall + per-rule accuracy.

Run: python benchmarks/bench_attribution.py
"""
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from agentdiff.attribution import engine
from agentdiff.compare import compare_all
from agentdiff.capture.events import CallSite, CanonicalLLMCall, LLMRequestEvent
from agentdiff.structure.structure_yaml import AgentEntry, StructureDoc, ToolEntry
from agentdiff.trajectory import Trajectory, TrajectorySet

INSTANCES = 10  # per change type

STRUCT = StructureDoc(
    agents=[AgentEntry(name="Research", function="research_agent", file="agent.py", line=3)],
    tools=[ToolEntry(name="search", function="web_search", file="tools.py", line=1)],
)


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _traj(tag, prompt, model, tools, fired=True):
    events = []
    if fired:
        events.append(
            LLMRequestEvent(
                call_id=uuid4(),
                canonical=CanonicalLLMCall(
                    provider="anthropic", model=model, system=prompt,
                    sampling_params={"temperature": 0.5}, tools=tools,
                ),
                captured_by="sdk_shim",
                callsite=CallSite(file="agent.py", function="research_agent", line=5),
                inferred_agent="Research",
            )
        )
    return Trajectory(test_case_id="tc", version_tag=tag, input={}, events=events)


def _trajectories(b_prompt, c_prompt, b_model, c_model, b_tools, c_tools):
    # baseline fires 20/20; candidate fires 10/20 → significant invocation drop.
    baseline = [_traj("baseline", b_prompt, b_model, b_tools) for _ in range(20)]
    candidate = [_traj("candidate", c_prompt, c_model, c_tools) for _ in range(10)]
    candidate += [_traj("candidate", c_prompt, c_model, c_tools, fired=False) for _ in range(10)]
    return baseline, candidate


def _agent_src(prompt, model, body_marker):
    return (
        "import anthropic\n"
        "import helper\n"
        f'PROMPT = "{prompt}"\n'
        f'MODEL = "{model}"\n'
        "def research_agent(query):\n"
        f"    _ = {body_marker}\n"
        "    client = anthropic.Anthropic()\n"
        "    return client.messages.create(model=MODEL, system=PROMPT, messages=[])\n"
    )


def _setup_repo(root: Path, prompt, model, body_marker, tools_src, helper_src):
    (root / "agent.py").write_text(_agent_src(prompt, model, body_marker))
    (root / "tools.py").write_text(tools_src)
    (root / "helper.py").write_text(helper_src)
    _git(["init"], root)
    _git(["config", "user.email", "b@b.com"], root)
    _git(["config", "user.name", "b"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "baseline"], root)


def _run_scenario(kind: str, i: int) -> tuple[str, str | None]:
    """Return (primary_rule, primary_target) for one scenario instance."""
    SEARCH = [{"name": "search"}]
    SEARCH2 = [{"name": "search"}, {"name": "calc"}]
    base_prompt = f"You are baseline assistant {i}"
    cand_prompt = f"You are candidate assistant {i}"
    base_tools_src = "def web_search(q):\n    return q\n"
    cand_tools_src = "def web_search(q):\n    return q\ndef calc(x):\n    return x\n"
    base_helper = f"VALUE = {i}\n"
    cand_helper = f"VALUE = {i + 100}\n"

    with tempfile.TemporaryDirectory(prefix="adbench-") as td:
        root = Path(td)
        # Baseline repo (committed state).
        _setup_repo(root, base_prompt, "claude-base", "0", base_tools_src, base_helper)

        if kind == "prompt":
            (root / "agent.py").write_text(_agent_src(cand_prompt, "claude-base", "0"))
            b_tr, c_tr = _trajectories(base_prompt, cand_prompt, "claude-base", "claude-base", SEARCH, SEARCH)
        elif kind == "code":
            (root / "agent.py").write_text(_agent_src(base_prompt, "claude-base", str(i + 1)))
            b_tr, c_tr = _trajectories(base_prompt, base_prompt, "claude-base", "claude-base", SEARCH, SEARCH)
        elif kind == "model":
            (root / "agent.py").write_text(_agent_src(base_prompt, "claude-cand", "0"))
            b_tr, c_tr = _trajectories(base_prompt, base_prompt, "claude-base", "claude-cand", SEARCH, SEARCH)
        elif kind == "tool":
            (root / "tools.py").write_text(cand_tools_src)
            b_tr, c_tr = _trajectories(base_prompt, base_prompt, "claude-base", "claude-base", SEARCH, SEARCH2)
        elif kind == "reachable":
            (root / "helper.py").write_text(cand_helper)
            b_tr, c_tr = _trajectories(base_prompt, base_prompt, "claude-base", "claude-base", SEARCH, SEARCH)
        else:
            raise ValueError(kind)

        comparison = compare_all(
            TrajectorySet(version_tag="baseline", trajectories=b_tr),
            TrajectorySet(version_tag="candidate", trajectories=c_tr),
            STRUCT, ["tc"],
        )
        result = engine.attribute(
            comparison=comparison, structure=STRUCT,
            baseline_trajectories=b_tr, candidate_trajectories=c_tr,
            repo_root=root, baseline_ref="HEAD", candidate_ref=None, llm_client=None,
        )
        if not result.attributions or result.attributions[0].primary is None:
            return "<none>", None
        p = result.attributions[0].primary
        return p.rule, p.target_path


def main() -> None:
    expected = {
        "prompt": ("direct_prompt_change", "agent.py"),
        "code": ("code_change", "agent.py"),
        "model": ("model_config_change", "agent.py"),
        "tool": ("tool_schema_change", "tools.py"),
        "reachable": ("reachable_change", "helper.py"),
    }
    total_correct = total = 0
    for kind, (exp_rule, exp_file) in expected.items():
        correct = 0
        for i in range(INSTANCES):
            rule, target = _run_scenario(kind, i)
            if rule == exp_rule and target == exp_file:
                correct += 1
        total_correct += correct
        total += INSTANCES
        print(f"{kind:10s} | expect {exp_rule:22s}→{exp_file:9s} | {correct}/{INSTANCES} correct")
    print(f"\nOVERALL attribution accuracy: {total_correct}/{total} = {total_correct / total:.1%}")


if __name__ == "__main__":
    main()
