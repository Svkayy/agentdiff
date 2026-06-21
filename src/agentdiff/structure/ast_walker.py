"""Walk a Python project and collect candidate functions for structure inference."""
import ast
from pathlib import Path
from typing import Iterator

from pydantic import BaseModel, Field

_SKIP_DIRS = {
    ".venv", "venv", ".env", "__pycache__", ".git", ".agentdiff",
    "node_modules", "dist", "build", ".tox", ".mypy_cache", ".ruff_cache",
}

_LLM_SDK_MODULES = {"anthropic", "openai", "mcp", "litellm", "together", "cohere"}

# Attribute names that signal an LLM invocation call chain.
_LLM_CALL_ATTRS = {"create", "complete", "generate"}
_LLM_CHAIN_ATTRS = {"messages", "completions", "chat", "responses"}


class CandidateFunction(BaseModel):
    name: str
    file: str           # relative to project root
    line: int
    is_async: bool
    decorators: list[str] = Field(default_factory=list)
    docstring: str | None = None
    calls_llm: bool = False
    has_agentdiff_tool_decorator: bool = False
    module_imports_llm_sdk: bool = False
    class_name: str | None = None   # Set for class methods; None for top-level functions


def walk_project(root: Path) -> list[CandidateFunction]:
    """Return CandidateFunction entries for top-level functions and class methods."""
    candidates: list[CandidateFunction] = []
    for py_file in _iter_py_files(root):
        rel = py_file.relative_to(root)
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        imports_sdk = _module_imports_llm_sdk(tree)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                candidates.append(_extract(node, str(rel), imports_sdk))
            elif isinstance(node, ast.ClassDef):
                for child in ast.iter_child_nodes(node):
                    if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    cand = _extract(child, str(rel), imports_sdk, class_name=node.name)
                    # Only include class methods that call an LLM or have the tool decorator;
                    # plain helpers inside a class add noise and are skipped.
                    if cand.calls_llm or cand.has_agentdiff_tool_decorator:
                        candidates.append(cand)

    return candidates


def _extract(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    file: str,
    imports_sdk: bool,
    class_name: str | None = None,
) -> CandidateFunction:
    decorators = [_decorator_name(d) for d in node.decorator_list]
    docstring = ast.get_docstring(node)

    visitor = _LLMCallVisitor()
    for child in ast.iter_child_nodes(node):
        visitor.visit(child)

    # Qualify name for class methods so it is unique across the file.
    name = f"{class_name}.{node.name}" if class_name else node.name

    return CandidateFunction(
        name=name,
        file=file,
        line=node.lineno,
        is_async=isinstance(node, ast.AsyncFunctionDef),
        decorators=decorators,
        docstring=docstring,
        calls_llm=visitor.found,
        has_agentdiff_tool_decorator=_has_tool_decorator(node),
        module_imports_llm_sdk=imports_sdk,
        class_name=class_name,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iter_py_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        yield path


def _module_imports_llm_sdk(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _LLM_SDK_MODULES:
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in _LLM_SDK_MODULES:
                return True
    return False


def _has_tool_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in node.decorator_list:
        name = _decorator_name(dec)
        if name in ("agentdiff.tool", "tool"):
            return True
    return False


def _decorator_name(node: ast.expr) -> str:
    """Best-effort: return a dotted name string for a decorator expression."""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts = []
        cur: ast.expr = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    return ""


def _attr_chain(node: ast.expr) -> list[str]:
    """Extract attribute names from a.b.c → ['a', 'b', 'c']."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return list(reversed(parts))


class _LLMCallVisitor(ast.NodeVisitor):
    """Detects direct LLM SDK calls in a function body (does not recurse into nested defs)."""

    def __init__(self) -> None:
        self.found = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        pass  # stop recursion into nested functions

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        pass  # stop recursion

    def visit_Call(self, node: ast.Call) -> None:
        if not self.found:
            chain = _attr_chain(node.func)
            chain_set = set(chain)
            if chain_set & _LLM_CALL_ATTRS and chain_set & _LLM_CHAIN_ATTRS:
                self.found = True
        self.generic_visit(node)
