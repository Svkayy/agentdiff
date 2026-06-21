"""Diff two sides' manifests into per-agent deltas."""
from typing import Any

from pydantic import BaseModel, Field

from agentdiff.attribution.manifest import AgentManifest


class ManifestDelta(BaseModel):
    agent_name: str
    function: str

    prompt_changed: bool = False
    prompt_files: list[str] = Field(default_factory=list)

    code_changed: bool = False
    code_file: str = ""

    model_params_changed: bool = False
    model_params_before: dict[str, Any] = Field(default_factory=dict)
    model_params_after: dict[str, Any] = Field(default_factory=dict)

    tools_changed: bool = False
    tools_before: list[str] = Field(default_factory=list)
    tools_after: list[str] = Field(default_factory=list)

    def has_any_change(self) -> bool:
        return (
            self.prompt_changed
            or self.code_changed
            or self.model_params_changed
            or self.tools_changed
        )


def _core_params(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if k != "tools"}


def diff_manifests(
    baseline: dict[str, AgentManifest],
    candidate: dict[str, AgentManifest],
) -> dict[str, ManifestDelta]:
    """Compare baseline vs candidate manifests, keyed by agent function."""
    out: dict[str, ManifestDelta] = {}
    for func, b in baseline.items():
        c = candidate.get(func)
        if c is None:
            continue
        b_tools = list(b.model_params.get("tools", []))
        c_tools = list(c.model_params.get("tools", []))
        out[func] = ManifestDelta(
            agent_name=b.agent_name,
            function=func,
            prompt_changed=b.prompt_content_hash != c.prompt_content_hash,
            prompt_files=sorted(set(b.prompt_files) | set(c.prompt_files)),
            code_changed=bool(b.code_hash) and bool(c.code_hash) and b.code_hash != c.code_hash,
            code_file=c.code_file or b.code_file,
            model_params_changed=_core_params(b.model_params) != _core_params(c.model_params),
            model_params_before=b.model_params,
            model_params_after=c.model_params,
            tools_changed=b_tools != c_tools,
            tools_before=b_tools,
            tools_after=c_tools,
        )
    return out
