"""Attribution engine: behavioral deltas + manifest diff + git diff → attributions.

For every non-passing agent invocation delta in the ComparisonResult, build both
sides' manifests, diff them, run the rule pipeline against the git diff, rank the
results, and optionally attach an LLM explanation for the primary cause.
"""
from pathlib import Path

from pydantic import BaseModel, Field

from agentdiff.attribution.git_diff import collect_git_diff
from agentdiff.attribution.manifest import build_manifest_for_side
from agentdiff.attribution.manifest_diff import ManifestDelta, diff_manifests
from agentdiff.attribution.rules import Attribution, apply_rules
from agentdiff.compare import ComparisonResult
from agentdiff.structure.structure_yaml import StructureDoc
from agentdiff.trajectory import Trajectory


class BehavioralAttribution(BaseModel):
    test_case_id: str
    agent_name: str
    function: str
    metric: str
    delta_summary: str
    verdict: str
    primary: Attribution | None = None
    alternatives: list[Attribution] = Field(default_factory=list)
    explanation: str | None = None


class AttributionResult(BaseModel):
    attributions: list[BehavioralAttribution] = Field(default_factory=list)


def attribute(
    comparison: ComparisonResult,
    structure: StructureDoc,
    baseline_trajectories: list[Trajectory],
    candidate_trajectories: list[Trajectory],
    repo_root: Path,
    baseline_ref: str,
    candidate_ref: str | None,
    llm_client=None,
) -> AttributionResult:
    """Attribute every non-passing agent invocation delta to a changed file.

    ``candidate_ref=None`` means the working tree.
    """
    repo_root = Path(repo_root)
    git_arg = candidate_ref if candidate_ref else "working"
    git_diff = collect_git_diff(baseline_ref, git_arg, repo_root)

    baseline_manifests = build_manifest_for_side(
        repo_root, baseline_ref, baseline_trajectories, structure
    )
    candidate_manifests = build_manifest_for_side(
        repo_root, candidate_ref, candidate_trajectories, structure
    )
    deltas = diff_manifests(baseline_manifests, candidate_manifests)

    results: list[BehavioralAttribution] = []
    for tcc in comparison.test_case_comparisons:
        for d in tcc.agent_invocation_deltas:
            if d.verdict == "pass":
                continue

            summary = (
                f"invocation rate {d.baseline_rate:.0%} → {d.candidate_rate:.0%} "
                f"({d.delta:+.0%})"
            )
            md = deltas.get(d.function)
            ba = BehavioralAttribution(
                test_case_id=tcc.test_case_id,
                agent_name=d.agent_name,
                function=d.function,
                metric="invocation_rate",
                delta_summary=summary,
                verdict=d.verdict,
            )

            if md is not None:
                reachable_changed = _reachable_changed_files(repo_root, md.code_file, git_diff)
                attrs = sorted(
                    apply_rules(md, git_diff, structure, reachable_changed),
                    key=lambda a: a.weight,
                    reverse=True,
                )
                if attrs:
                    ba.primary = attrs[0]
                    ba.alternatives = attrs[1:]

            if ba.primary is not None and llm_client is not None:
                from agentdiff.attribution.explainer import explain
                ba.explanation = explain(
                    llm_client, ba.agent_name, ba.delta_summary, ba.verdict, ba.primary
                )

            results.append(ba)

    return AttributionResult(attributions=results)


def _reachable_changed_files(repo_root: Path, code_file: str, git_diff: dict[str, str]) -> list[str]:
    """Changed files statically reachable from the agent's code file (working tree)."""
    if not code_file or not git_diff:
        return []
    try:
        from agentdiff.attribution.reachability import reachable_files
        reachable = reachable_files(repo_root, code_file)
    except Exception:
        return []
    return sorted(set(git_diff) & reachable)


def attribute_observed(
    comparison: ComparisonResult,
    structure: StructureDoc,
    baseline_trajectories: list[Trajectory],
    candidate_trajectories: list[Trajectory],
    repo_root: Path,
) -> AttributionResult:
    """Attribution from captured data only — no git baseline.

    Detects prompt / model / tool changes between two captures from the observed
    trajectories (those fields are captured, not read from git). It cannot produce
    a code-diff hunk, since the "before" source is gone by diff time — use the
    git-baseline ``attribute`` path for that. Powers the low-friction
    ``agentdiff diff`` flow.
    """
    repo_root = Path(repo_root)
    baseline_manifests = build_manifest_for_side(repo_root, None, baseline_trajectories, structure)
    candidate_manifests = build_manifest_for_side(repo_root, None, candidate_trajectories, structure)
    deltas = diff_manifests(baseline_manifests, candidate_manifests)

    results: list[BehavioralAttribution] = []
    for tcc in comparison.test_case_comparisons:
        for d in tcc.agent_invocation_deltas:
            if d.verdict == "pass":
                continue
            summary = (
                f"invocation rate {d.baseline_rate:.0%} → {d.candidate_rate:.0%} "
                f"({d.delta:+.0%})"
            )
            reason, cause = _observed_reason(deltas.get(d.function), d.agent_name)
            results.append(
                BehavioralAttribution(
                    test_case_id=tcc.test_case_id,
                    agent_name=d.agent_name,
                    function=d.function,
                    metric="invocation_rate",
                    delta_summary=summary,
                    verdict=d.verdict,
                    primary=Attribution(
                        rule="observed_change",
                        target_path=cause or "",
                        hunk=None,
                        weight=0.5,
                        reason=reason,
                    ),
                    explanation=reason,
                )
            )
    return AttributionResult(attributions=results)


def _observed_reason(md: ManifestDelta | None, agent_name: str) -> tuple[str, str | None]:
    """A plain-English cause from observed manifest changes (no git hunk)."""
    if md is not None and md.prompt_changed:
        return (
            f"The system prompt observed for {agent_name} changed between the two captures.",
            md.prompt_files[0] if md.prompt_files else None,
        )
    if md is not None and md.model_params_changed:
        return (
            f"The model or sampling parameters for {agent_name} changed between the two captures.",
            None,
        )
    if md is not None and md.tools_changed:
        return (f"The tool set available to {agent_name} changed between the two captures.", None)
    return (
        f"{agent_name}'s behavior changed, but the cause isn't visible without a git "
        "baseline. Run `agentdiff diff --baseline <ref>` for the code diff.",
        None,
    )
