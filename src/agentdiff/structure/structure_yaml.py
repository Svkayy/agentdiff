"""StructureDoc model and load/save helpers for .agentdiff/structure.yaml."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

_AGENTDIFF_DIR = ".agentdiff"
_STRUCTURE_FILE = "structure.yaml"


class AgentEntry(BaseModel):
    name: str
    function: str
    file: str
    line: int


class ToolEntry(BaseModel):
    name: str
    function: str
    file: str
    line: int


class EntryPointEntry(BaseModel):
    function: str
    file: str
    line: int


class StructureDoc(BaseModel):
    version: str = "1"
    agents: list[AgentEntry] = Field(default_factory=list)
    tools: list[ToolEntry] = Field(default_factory=list)
    entry_points: list[EntryPointEntry] = Field(default_factory=list)

    def agent_names_for_functions(self) -> dict[str, str]:
        """Return mapping from function name → agent name for fast lookup at capture time.

        For class methods stored as ``ClassName.method_name``, the simple method
        name is also registered (without overriding an exact-match entry) so
        that Python call-stack frames — which only carry the bare method name —
        still resolve correctly.
        """
        result: dict[str, str] = {}
        for a in self.agents:
            result[a.function] = a.name
            # ClassName.method_name → also register "method_name" as a fallback.
            simple = a.function.rsplit(".", 1)[-1]
            if simple != a.function:
                result.setdefault(simple, a.name)
        return result

    def tool_names_for_functions(self) -> dict[str, str]:
        return {t.function: t.name for t in self.tools}


@dataclass
class StructureDiff:
    """Summary of what changed between an existing structure.yaml and a fresh scan."""

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)


def _identity_key(file: str, function: str) -> str:
    """Identity key for merge matching: `file:qualname` (qualname = ClassName.method or function)."""
    return f"{file}:{function}"


def merge_structures(existing: StructureDoc, fresh: StructureDoc) -> tuple[StructureDoc, StructureDiff]:
    """Merge a freshly-inferred StructureDoc into an existing one.

    Identity is `file:qualname` (a function's `file` + `function` fields). For entries
    whose identity key exists in both docs, the *existing* entry is kept as-is — this
    preserves any user edits to display names (``AgentEntry.name`` / ``ToolEntry.name``)
    even if the fresh scan reclassified the entry into a different role (agent/tool/
    entry_point), since a role change is itself informative and shouldn't silently drop
    a user's naming work when possible. New identities found only in ``fresh`` are added.
    Identities present in ``existing`` but absent from ``fresh`` are dropped.
    """
    existing_by_key: dict[str, tuple[str, Any]] = {}
    for a in existing.agents:
        existing_by_key[_identity_key(a.file, a.function)] = ("agent", a)
    for t in existing.tools:
        existing_by_key[_identity_key(t.file, t.function)] = ("tool", t)
    for e in existing.entry_points:
        existing_by_key[_identity_key(e.file, e.function)] = ("entry_point", e)

    fresh_keys: set[str] = set()
    for a in fresh.agents:
        fresh_keys.add(_identity_key(a.file, a.function))
    for t in fresh.tools:
        fresh_keys.add(_identity_key(t.file, t.function))
    for e in fresh.entry_points:
        fresh_keys.add(_identity_key(e.file, e.function))

    merged_agents: list[AgentEntry] = []
    merged_tools: list[ToolEntry] = []
    merged_entry_points: list[EntryPointEntry] = []

    added: list[str] = []
    removed: list[str] = []
    kept: list[str] = []

    # Entries from fresh: kept (reuse existing entry to preserve edits) or added (new).
    for a in fresh.agents:
        key = _identity_key(a.file, a.function)
        if key in existing_by_key:
            role, entry = existing_by_key[key]
            if role == "agent":
                merged_agents.append(entry)
            else:
                # Role changed to "agent" in the fresh scan; carry over the
                # user's display name (if the prior role had one) but adopt
                # the new role/location.
                prior_name = entry.name if role == "tool" else a.name
                merged_agents.append(AgentEntry(
                    name=prior_name, function=a.function, file=a.file, line=a.line,
                ))
            kept.append(key)
        else:
            merged_agents.append(a)
            added.append(key)

    for t in fresh.tools:
        key = _identity_key(t.file, t.function)
        if key in existing_by_key:
            role, entry = existing_by_key[key]
            if role == "tool":
                merged_tools.append(entry)
            else:
                prior_name = entry.name if role == "agent" else t.name
                merged_tools.append(ToolEntry(
                    name=prior_name, function=t.function, file=t.file, line=t.line,
                ))
            kept.append(key)
        else:
            merged_tools.append(t)
            added.append(key)

    for e in fresh.entry_points:
        key = _identity_key(e.file, e.function)
        if key in existing_by_key:
            merged_entry_points.append(e)
            kept.append(key)
        else:
            merged_entry_points.append(e)
            added.append(key)

    # Identities that existed before but vanished from the fresh scan.
    for key in existing_by_key:
        if key not in fresh_keys:
            removed.append(key)

    merged = StructureDoc(
        version=existing.version,
        agents=merged_agents,
        tools=merged_tools,
        entry_points=merged_entry_points,
    )
    diff = StructureDiff(added=sorted(added), removed=sorted(removed), kept=sorted(kept))
    return merged, diff


def structure_path(project_root: Path) -> Path:
    return project_root / _AGENTDIFF_DIR / _STRUCTURE_FILE


def save(doc: StructureDoc, project_root: Path) -> Path:
    path = structure_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            _to_dict(doc),
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
    return path


def load(project_root: Path) -> StructureDoc | None:
    path = structure_path(project_root)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        data: Any = yaml.safe_load(f)
    if not data:
        return StructureDoc()
    return StructureDoc.model_validate(data)


def load_nearest(cwd: Path | None = None) -> StructureDoc | None:
    """Walk up from cwd searching for .agentdiff/structure.yaml."""
    current = Path(cwd or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        doc = load(directory)
        if doc is not None:
            return doc
    return None


def _to_dict(doc: StructureDoc) -> dict:
    return {
        "version": doc.version,
        "agents": [a.model_dump() for a in doc.agents],
        "tools": [t.model_dump() for t in doc.tools],
        "entry_points": [e.model_dump() for e in doc.entry_points],
    }
