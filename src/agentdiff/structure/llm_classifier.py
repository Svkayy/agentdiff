"""Optional LLM refinement pass for structure classification (--llm flag)."""
import json
from typing import Any

from agentdiff.structure.ast_walker import CandidateFunction
from agentdiff.structure.structure_yaml import (
    AgentEntry, EntryPointEntry, StructureDoc, ToolEntry,
)

_SYSTEM_PROMPT = """\
You are analyzing a Python AI agent codebase. You will be given a list of candidate functions \
and must classify each one as "agent", "tool", "entry_point", or "irrelevant".

Definitions:
- agent: a function that drives an LLM interaction loop (calls an LLM, may call tools, returns a result)
- tool: a function dispatched by an agent to perform a specific action (search, fetch, compute, etc.)
- entry_point: the top-level function that kicks off a run (e.g. main(), run())
- irrelevant: helper, utility, or unrelated function

Return ONLY a JSON array. Each element: {"function": "<name>", "file": "<file>", "role": "<role>", "name": "<human_readable_name>"}.
"""


def refine(
    heuristic_doc: StructureDoc,
    candidates: list[CandidateFunction],
    api_key: str,
    model: str = "claude-3-5-haiku-20241022",
) -> StructureDoc:
    """Call the Anthropic API to refine the heuristic classification."""
    try:
        import anthropic
    except ImportError:
        return heuristic_doc

    prompt = _build_prompt(candidates)
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text if response.content else ""
    return _parse_response(raw, candidates, heuristic_doc)


def _build_prompt(candidates: list[CandidateFunction]) -> str:
    items = [
        {
            "name": fn.name,
            "file": fn.file,
            "line": fn.line,
            "is_async": fn.is_async,
            "decorators": fn.decorators,
            "docstring": fn.docstring or "",
            "calls_llm": fn.calls_llm,
            "has_agentdiff_tool_decorator": fn.has_agentdiff_tool_decorator,
            "module_imports_llm_sdk": fn.module_imports_llm_sdk,
        }
        for fn in candidates
    ]
    return f"Classify these functions:\n\n{json.dumps(items, indent=2)}"


def _parse_response(
    raw: str,
    candidates: list[CandidateFunction],
    heuristic_doc: StructureDoc,
) -> StructureDoc:
    """Parse the LLM response into a StructureDoc.

    Falls back to *heuristic_doc* (not an empty doc) if the response cannot be
    parsed, so valid heuristic classifications are never silently discarded.
    """
    # Extract JSON array from response (LLM might wrap it in markdown).
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start == -1 or end == 0:
        return heuristic_doc

    try:
        items: list[dict[str, Any]] = json.loads(raw[start:end])
    except json.JSONDecodeError:
        return heuristic_doc

    # Key by (name, file) so duplicate function names in different files don't collide.
    fn_map: dict[tuple[str, str], CandidateFunction] = {
        (fn.name, fn.file): fn for fn in candidates
    }
    agents, tools, entry_points = [], [], []

    for item in items:
        fn_name = item.get("function", "")
        fn_file = item.get("file", "")
        role = item.get("role", "irrelevant")
        display_name = item.get("name", fn_name)

        # Primary lookup by (name, file) — handles duplicates correctly.
        fn = fn_map.get((fn_name, fn_file))
        # Fallback: name-only search in case the LLM returned a slightly
        # different file path (e.g., leading "./" or Windows separators).
        if fn is None:
            fn = next((c for c in candidates if c.name == fn_name), None)
        if fn is None:
            continue

        if role == "agent":
            agents.append(AgentEntry(name=display_name, function=fn_name, file=fn.file, line=fn.line))
        elif role == "tool":
            tools.append(ToolEntry(name=display_name, function=fn_name, file=fn.file, line=fn.line))
        elif role == "entry_point":
            entry_points.append(EntryPointEntry(function=fn_name, file=fn.file, line=fn.line))

    return StructureDoc(agents=agents, tools=tools, entry_points=entry_points)
