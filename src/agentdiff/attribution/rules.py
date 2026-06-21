"""The 5 v0 attribution rules.

Each rule inspects a ManifestDelta + the git diff and emits zero or more
Attributions (a target file, an optional diff hunk, a confidence weight, and a
reason). The engine ranks them by weight; the highest is the primary cause.

Rule 5 (reachable_change) is the v0 fallback — full reachability analysis is v1.
"""
from pydantic import BaseModel

from agentdiff.attribution.manifest_diff import ManifestDelta
from agentdiff.structure.structure_yaml import StructureDoc


class Attribution(BaseModel):
    rule: str
    target_path: str
    hunk: str | None = None
    weight: float
    reason: str


def _rule_direct_prompt_change(md: ManifestDelta, git_diff: dict[str, str]) -> list[Attribution]:
    if not md.prompt_changed:
        return []
    hits = [f for f in md.prompt_files if f in git_diff]
    if hits:
        return [
            Attribution(
                rule="direct_prompt_change",
                target_path=f,
                hunk=git_diff[f],
                weight=0.9,
                reason=(
                    f"The system prompt for agent '{md.agent_name}' changed, and "
                    f"`{f}` (which contains it) was modified."
                ),
            )
            for f in hits
        ]
    # Prompt changed but lives inline in the agent's code file.
    if md.code_file in git_diff:
        return [
            Attribution(
                rule="direct_prompt_change",
                target_path=md.code_file,
                hunk=git_diff[md.code_file],
                weight=0.75,
                reason=(
                    f"The system prompt for agent '{md.agent_name}' changed; it appears "
                    f"inline in `{md.code_file}`."
                ),
            )
        ]
    return []


def _rule_code_change(md: ManifestDelta, git_diff: dict[str, str]) -> list[Attribution]:
    if md.code_changed and md.code_file in git_diff:
        return [
            Attribution(
                rule="code_change",
                target_path=md.code_file,
                hunk=git_diff[md.code_file],
                weight=0.8,
                reason=(
                    f"The body of agent '{md.agent_name}' (`{md.function}`) changed in "
                    f"`{md.code_file}`."
                ),
            )
        ]
    return []


def _rule_model_config_change(md: ManifestDelta, git_diff: dict[str, str]) -> list[Attribution]:
    if not md.model_params_changed:
        return []
    before = {k: v for k, v in md.model_params_before.items() if k != "tools"}
    after = {k: v for k, v in md.model_params_after.items() if k != "tools"}
    return [
        Attribution(
            rule="model_config_change",
            target_path=md.code_file,
            hunk=git_diff.get(md.code_file),
            weight=0.7,
            reason=(
                f"Model configuration for agent '{md.agent_name}' changed: "
                f"{before} → {after}."
            ),
        )
    ]


def _rule_tool_schema_change(
    md: ManifestDelta, git_diff: dict[str, str], structure: StructureDoc
) -> list[Attribution]:
    if not md.tools_changed:
        return []
    tool_files = sorted({t.file for t in structure.tools})
    hits = [f for f in tool_files if f in git_diff]
    if hits:
        return [
            Attribution(
                rule="tool_schema_change",
                target_path=f,
                hunk=git_diff[f],
                weight=0.6,
                reason=(
                    f"The set of tools available to agent '{md.agent_name}' changed; "
                    f"`{f}` was modified. ({md.tools_before} → {md.tools_after})"
                ),
            )
            for f in hits
        ]
    return [
        Attribution(
            rule="tool_schema_change",
            target_path=md.code_file,
            hunk=git_diff.get(md.code_file),
            weight=0.5,
            reason=(
                f"The set of tools used by agent '{md.agent_name}' changed "
                f"({md.tools_before} → {md.tools_after})."
            ),
        )
    ]


def _rule_reachable_change(
    md: ManifestDelta,
    git_diff: dict[str, str],
    reachable_changed: list[str] | None = None,
) -> list[Attribution]:
    """Fallback: behavior changed but nothing direct matched.

    If ``reachable_changed`` (changed files statically reachable from the agent's
    code via the import graph) is provided and non-empty, attribute to one of those
    with higher confidence than the blind heuristic.
    """
    changed = sorted(git_diff.keys())
    if not changed:
        return []

    if reachable_changed:
        target = md.code_file if md.code_file in reachable_changed else reachable_changed[0]
        return [
            Attribution(
                rule="reachable_change",
                target_path=target,
                hunk=git_diff.get(target),
                weight=0.35,
                reason=(
                    f"Behavior of agent '{md.agent_name}' changed with no direct prompt, "
                    f"code, model, or tool change. `{target}` changed and is reachable from "
                    "the agent via the import graph, making it the likely cause."
                ),
            )
        ]

    target = md.code_file if md.code_file in git_diff else changed[0]
    return [
        Attribution(
            rule="reachable_change",
            target_path=target,
            hunk=git_diff.get(target),
            weight=0.2,
            reason=(
                f"Behavior of agent '{md.agent_name}' changed but no direct prompt, code, "
                f"model, or tool change matched, and no changed file was provably reachable. "
                f"A change in `{target}` is the likely cause (low-confidence heuristic)."
            ),
        )
    ]


def apply_rules(
    md: ManifestDelta,
    git_diff: dict[str, str],
    structure: StructureDoc,
    reachable_changed: list[str] | None = None,
) -> list[Attribution]:
    """Run all direct rules; fall back to reachable_change only if none fired."""
    attrs: list[Attribution] = []
    attrs += _rule_direct_prompt_change(md, git_diff)
    attrs += _rule_code_change(md, git_diff)
    attrs += _rule_model_config_change(md, git_diff)
    attrs += _rule_tool_schema_change(md, git_diff, structure)
    if not attrs:
        attrs += _rule_reachable_change(md, git_diff, reachable_changed)
    return attrs
