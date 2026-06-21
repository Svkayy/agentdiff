"""Classify CandidateFunction list into a StructureDoc using AST heuristics only."""
from agentdiff.structure.ast_walker import CandidateFunction
from agentdiff.structure.structure_yaml import (
    AgentEntry, EntryPointEntry, StructureDoc, ToolEntry,
)

_ENTRY_POINT_NAMES = {"main", "run", "start", "entrypoint", "entry_point"}
_AGENT_NAME_HINTS = {"agent", "run_agent", "invoke_agent", "execute_agent"}


def classify(candidates: list[CandidateFunction]) -> StructureDoc:
    agents: list[AgentEntry] = []
    tools: list[ToolEntry] = []
    entry_points: list[EntryPointEntry] = []

    for fn in candidates:
        role = _classify_one(fn)
        if role == "tool":
            tools.append(ToolEntry(
                name=fn.name,
                function=fn.name,
                file=fn.file,
                line=fn.line,
            ))
        elif role == "agent":
            agents.append(AgentEntry(
                name=fn.name,
                function=fn.name,
                file=fn.file,
                line=fn.line,
            ))
        elif role == "entry_point":
            entry_points.append(EntryPointEntry(
                function=fn.name,
                file=fn.file,
                line=fn.line,
            ))

    return StructureDoc(agents=agents, tools=tools, entry_points=entry_points)


def _classify_one(fn: CandidateFunction) -> str:
    # @agentdiff.tool / @tool decorator — definitive
    if fn.has_agentdiff_tool_decorator:
        return "tool"

    # Direct LLM calls in body — strong signal for agent
    if fn.calls_llm:
        return "agent"

    # Module imports LLM SDK + name strongly suggests an agent
    if fn.module_imports_llm_sdk and _name_hints_agent(fn.name):
        return "agent"

    # Well-known entry-point names (in files that don't call LLMs directly).
    # For class methods (ClassName.method_name) check the simple method name.
    simple_name = fn.name.lower().rsplit(".", 1)[-1]
    if simple_name in _ENTRY_POINT_NAMES:
        return "entry_point"

    return "irrelevant"


def _name_hints_agent(name: str) -> bool:
    lower = name.lower()
    return any(hint in lower for hint in _AGENT_NAME_HINTS)
