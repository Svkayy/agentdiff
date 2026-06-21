"""Dynamic agent manifest construction.

A manifest fingerprints one agent on one side (baseline or candidate) by combining
``structure.yaml`` with what was actually observed during sampling:
  - prompt content (observed ``canonical.system`` strings) + the files they live in
  - the agent function's source code hash (read at that side via git or disk)
  - model configuration (model, sampling params, tool names) observed in trajectories

The manifest reflects what happened, so the user declares nothing beyond structure.yaml.
"""
import ast
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agentdiff.structure.structure_yaml import StructureDoc
from agentdiff.trajectory import Trajectory

_PROMPT_SCAN_SUFFIXES = (".txt", ".md", ".py", ".yaml", ".yml", ".j2", ".jinja")


class AgentManifest(BaseModel):
    agent_name: str
    function: str
    code_file: str = ""
    code_hash: str = ""
    prompt_files: list[str] = Field(default_factory=list)
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    prompt_content_hash: str = ""
    model_params: dict[str, Any] = Field(default_factory=dict)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def read_source_at(repo_root: Path, ref: str | None, relpath: str) -> str | None:
    """Read a file's content at a given side. ``ref=None`` means the working tree."""
    if ref is None:
        p = Path(repo_root) / relpath
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
        return None
    try:
        return subprocess.check_output(
            ["git", "show", f"{ref}:{relpath}"],
            cwd=repo_root, text=True, stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None


def _tool_names(tools: list[dict] | None) -> list[str]:
    names: list[str] = []
    for t in tools or []:
        if not isinstance(t, dict):
            continue
        # Anthropic: {"name": ...}; OpenAI: {"type":"function","function":{"name":...}}
        name = t.get("name")
        if not name and isinstance(t.get("function"), dict):
            name = t["function"].get("name")
        if name:
            names.append(name)
    return sorted(names)


def _collect_observed_prompts(agent_name: str, trajectories: list[Trajectory]) -> list[str]:
    prompts: set[str] = set()
    for t in trajectories:
        for e in t.events:
            if getattr(e, "inferred_agent", None) != agent_name:
                continue
            canonical = getattr(e, "canonical", None)
            if canonical is not None and canonical.system:
                prompts.add(canonical.system)
    return sorted(prompts)


def _aggregate_model_params(agent_name: str, trajectories: list[Trajectory]) -> dict[str, Any]:
    """Most-common observed (model, sampling_params, tools) for the agent."""
    configs: Counter = Counter()
    rep: dict[tuple, dict[str, Any]] = {}
    for t in trajectories:
        for e in t.events:
            if getattr(e, "inferred_agent", None) != agent_name:
                continue
            c = getattr(e, "canonical", None)
            if c is None:
                continue
            tools = _tool_names(c.tools)
            key = (
                c.model,
                json.dumps(c.sampling_params, sort_keys=True, default=str),
                json.dumps(tools),
            )
            configs[key] += 1
            rep[key] = {"model": c.model, "sampling_params": c.sampling_params, "tools": tools}
    if not configs:
        return {"model": None, "sampling_params": {}, "tools": []}
    best_key, _ = configs.most_common(1)[0]
    return rep[best_key]


def _attribute_prompts_to_files(
    repo_root: Path, prompt_strings: list[str]
) -> tuple[list[str], dict[str, str]]:
    """Find which project files each observed prompt lives in (scans the working tree).

    Used to *name* the prompt's source file; change detection is done separately via
    prompt content hashing + the git diff.
    """
    repo_root = Path(repo_root)
    candidate_files: list[Path] = []
    for suffix in _PROMPT_SCAN_SUFFIXES:
        candidate_files.extend(repo_root.rglob(f"*{suffix}"))

    files: list[str] = []
    hashes: dict[str, str] = {}
    for prompt in prompt_strings:
        needle = prompt.strip()
        if not needle:
            continue
        matched = False
        for f in candidate_files:
            if any(part in {".git", ".agentdiff"} for part in f.parts):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if needle in content:
                rel = str(f.relative_to(repo_root))
                files.append(rel)
                hashes[rel] = _sha(content)
                matched = True
                break
        if not matched:
            synth = f"<inline-prompt:{_sha(prompt)[:8]}>"
            files.append(synth)
            hashes[synth] = _sha(prompt)
    # de-dup, keep order
    seen: set[str] = set()
    uniq: list[str] = []
    for name in files:
        if name not in seen:
            seen.add(name)
            uniq.append(name)
    return uniq, hashes


def _extract_function_source(source: str, qualname: str) -> str | None:
    """Return the source segment of a top-level function or ``Class.method``."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    parts = qualname.split(".")
    if len(parts) == 1:
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == parts[0]:
                return ast.get_source_segment(source, node)
        return None

    cls_name, method_name = parts[0], parts[-1]
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name:
                    return ast.get_source_segment(source, child)
    return None


def build_manifest_for_side(
    repo_root: Path,
    ref: str | None,
    trajectories: list[Trajectory],
    structure: StructureDoc,
) -> dict[str, AgentManifest]:
    """Build a manifest per agent (keyed by function) for one side."""
    out: dict[str, AgentManifest] = {}
    for agent in structure.agents:
        prompts = _collect_observed_prompts(agent.name, trajectories)
        prompt_files, prompt_hashes = _attribute_prompts_to_files(repo_root, prompts)

        source = read_source_at(repo_root, ref, agent.file)
        fn_source = _extract_function_source(source, agent.function) if source else None
        code_hash = _sha(fn_source) if fn_source else ""

        out[agent.function] = AgentManifest(
            agent_name=agent.name,
            function=agent.function,
            code_file=agent.file,
            code_hash=code_hash,
            prompt_files=prompt_files,
            prompt_hashes=prompt_hashes,
            prompt_content_hash=_sha("\n".join(prompts)),
            model_params=_aggregate_model_params(agent.name, trajectories),
        )
    return out
