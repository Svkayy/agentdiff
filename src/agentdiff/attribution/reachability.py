"""Static import-graph reachability.

Given an agent's source file, walk its imports transitively (within the project)
to determine which other project files it can reach. Used by attribution rule 5
to point at a changed file that is *actually* reachable from the agent, instead of
guessing. File-level (not symbol-level) — appropriate for naming a changed file.

Resolution is best-effort: external packages (anthropic, httpx, …) don't resolve
to project files and are ignored; unresolvable imports are skipped. Degrades to an
empty/partial set rather than raising.
"""
import ast
from pathlib import Path


def reachable_files(repo_root: Path | str, start_file: str, max_files: int = 500) -> set[str]:
    """Return the set of project-relative files reachable from ``start_file``
    (inclusive) by following imports."""
    repo_root = Path(repo_root)
    if not (repo_root / start_file).exists():
        return set()

    visited: set[str] = set()
    frontier: list[str] = [start_file]
    while frontier and len(visited) < max_files:
        rel = frontier.pop()
        if rel in visited:
            continue
        visited.add(rel)
        try:
            tree = ast.parse((repo_root / rel).read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError):
            continue
        for dotted, level in _imports(tree):
            for resolved in _resolve(repo_root, rel, dotted, level):
                if resolved not in visited:
                    frontier.append(resolved)
    return visited


def _imports(tree: ast.Module) -> list[tuple[str, int]]:
    """Collect (dotted_module, level) pairs. For `from a import b` we also yield
    `a.b` (level kept) so a submodule import resolves to its file."""
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, 0))
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            out.append((base, node.level))
            for alias in node.names:
                combined = f"{base}.{alias.name}" if base else alias.name
                out.append((combined, node.level))
    return out


def _resolve(repo_root: Path, current_rel: str, dotted: str, level: int) -> list[str]:
    """Resolve a (possibly relative) dotted module to existing project files."""
    if not dotted and level == 0:
        return []

    if level == 0:
        base = repo_root
        mod_path = dotted.replace(".", "/")
    else:
        # Relative import: level 1 = current package (dir of current file).
        pkg_parts = Path(current_rel).parent.parts
        up = level - 1
        if up > len(pkg_parts):
            return []
        base_parts = pkg_parts[: len(pkg_parts) - up] if up else pkg_parts
        base = repo_root.joinpath(*base_parts)
        mod_path = dotted.replace(".", "/")

    candidates = []
    if mod_path:
        candidates.append(base / f"{mod_path}.py")
        candidates.append(base / mod_path / "__init__.py")
    else:
        candidates.append(base / "__init__.py")

    out: list[str] = []
    for c in candidates:
        if c.exists() and c.is_file():
            try:
                out.append(str(c.relative_to(repo_root)))
            except ValueError:
                continue
    return out
